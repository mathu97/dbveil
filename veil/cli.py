from __future__ import annotations

import asyncio
import os
import re

try:
    import readline  # noqa: F401 — enables arrow-key line editing in prompts
except ImportError:
    pass

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .config import Config
from .executor import Executor
from .guard import check_query

app = typer.Typer(
    add_completion=False,
    help="veil — a local read-only, PII-redacting proxy for safe AI database access.",
)
console = Console()
err = Console(stderr=True)

_PII_HINTS = (
    "email", "e_mail", "phone", "mobile", "fax", "name", "first", "last",
    "address", "street", "city", "zip", "postal", "ssn", "social",
    "dob", "birth", "passport", "license", "ip_address",
)


def _resolve_env(url: str) -> str:
    return re.sub(r"\$\{([A-Z0-9_]+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), url)


def _load(path):
    try:
        return Config.load(path)
    except FileNotFoundError as exc:
        err.print(f"[red]config error:[/] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        err.print(f"[red]could not load config:[/] {exc}")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Print the veil version."""
    console.print(f"veil {__version__}")


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing config."),
) -> None:
    """Create a veil.yaml config, optionally auto-detecting PII columns."""
    path = Config.default_path()
    if path.exists() and not force:
        err.print(f"[yellow]{path} already exists. Use --force to overwrite.[/]")
        raise typer.Exit(1)

    console.print(Panel.fit("[bold]veil init[/] — let's set up safe database access", border_style="cyan"))
    db_url = typer.prompt(
        "Database URL (env refs like ${DATABASE_URL} are kept as-is in the file)",
        default="${DATABASE_URL}",
    )

    rules: list[tuple[str, str, str]] = []
    pii_tables: list[str] = []
    if typer.confirm("Introspect the database now to auto-suggest PII columns?", default=False):
        try:
            rules, pii_tables = asyncio.run(_introspect(_resolve_env(db_url)))
            console.print(f"[green]Found {len(rules)} likely PII column(s) across {len(pii_tables)} table(s).[/]")
        except Exception as exc:
            err.print(f"[yellow]Introspection failed ({exc}). Writing a template you can edit by hand.[/]")

    path.write_text(_render_config(db_url, rules, pii_tables))
    console.print(f"[bold green]Wrote {path}[/]")
    console.print("Next: [cyan]veil doctor[/] to verify, then [cyan]veil up[/] to run the proxy.")


@app.command()
def doctor(
    config: str = typer.Option(None, "--config", "-c", help="Path to veil.yaml."),
) -> None:
    """Verify the guard, database connectivity, and read-only enforcement."""
    cfg = _load(config)

    table = Table(title="veil doctor", show_header=True, header_style="bold")
    table.add_column("check")
    table.add_column("result")

    guard_ok = (
        check_query("SELECT 1").allowed
        and not check_query("DROP TABLE users").allowed
        and not check_query("UPDATE t SET x = 1").allowed
        and not check_query("WITH w AS (DELETE FROM t RETURNING *) SELECT * FROM w").allowed
        and not check_query("SELECT 1; DROP TABLE t").allowed
    )
    table.add_row("read-only guard (SELECT allowed, writes blocked)", _mark(guard_ok))

    conn_ok = False
    readonly_ok = False
    detail = ""
    try:
        conn_ok, readonly_ok = asyncio.run(_probe(cfg))
    except Exception as exc:
        detail = str(exc)

    table.add_row("database connection", _mark(conn_ok) + (f"  [dim]{detail}[/]" if detail else ""))
    table.add_row("server-side READ ONLY transaction rejects writes", _mark(readonly_ok))

    console.print(table)
    if not (guard_ok and conn_ok and readonly_ok):
        raise typer.Exit(1)


@app.command(name="test-query")
def test_query(
    sql: str = typer.Argument(..., help="A read-only SQL query to run through veil."),
    config: str = typer.Option(None, "--config", "-c"),
) -> None:
    """Run one query through the full guard + redact pipeline and print the result."""
    cfg = _load(config)
    outcome = asyncio.run(_run_one(cfg, sql))

    if outcome.blocked_reason:
        console.print(Panel(f"[bold red]BLOCKED[/]\n{outcome.blocked_reason}", border_style="red"))
        raise typer.Exit(1)
    if outcome.error:
        console.print(Panel(f"[bold red]ERROR[/]\n{outcome.error}", border_style="red"))
        raise typer.Exit(1)

    from .serialize import to_jsonable

    table = Table(show_header=True, header_style="bold")
    for col in outcome.columns:
        table.add_column(str(col))
    from rich.markup import escape

    for row in to_jsonable(outcome.rows):
        table.add_row(*[("∅" if c is None else escape(str(c))) for c in row])
    console.print(table)
    console.print(
        f"[dim]{outcome.row_count} row(s) · {outcome.redactions} redaction(s)"
        f"{' · truncated' if outcome.truncated else ''} · {outcome.duration_ms:.0f} ms[/]"
    )


@app.command()
def up(
    config: str = typer.Option(None, "--config", "-c", help="Path to veil.yaml."),
) -> None:
    """Run the MCP proxy on stdio (this is what Claude Code connects to)."""
    cfg = _load(config)
    err.print(
        f"[bold green]veil[/] up · stdio · guard=read-only · "
        f"redact={'on' if cfg.redact.columns or cfg.redact.ner.enabled else 'patterns-only'} · "
        f"audit→{cfg.audit_log}"
    )
    from .mcp_server import build_server

    build_server(cfg).run()


@app.command()
def monitor(
    config: str = typer.Option(None, "--config", "-c"),
) -> None:
    """Open a live TUI tailing the audit log (allowed / blocked / redactions)."""
    cfg = _load(config)
    try:
        from .tui import run_monitor
    except ImportError:
        err.print("[yellow]TUI not installed. Run: pip install 'dbveil[tui]'[/]")
        raise typer.Exit(1)
    run_monitor(cfg.audit_log)


async def _introspect(dsn: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    ex = Executor(dsn)
    rs = await ex._fetch_meta(
        "SELECT table_schema, table_name, column_name "
        "FROM information_schema.columns "
        "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
        "ORDER BY table_schema, table_name, ordinal_position"
    )
    await ex.close()

    rules: list[tuple[str, str, str]] = []
    pii_tables: set[str] = set()
    seen: set[str] = set()
    for schema, tname, col in rs.rows:
        low = col.lower()
        if any(h in low for h in _PII_HINTS):
            if col not in seen:
                strategy = "hash" if ("email" in low or "id" in low) else "mask"
                rules.append((col, strategy, ""))
                seen.add(col)
            pii_tables.add(tname)
    return rules, sorted(pii_tables)


async def _probe(cfg: Config) -> tuple[bool, bool]:
    ex = Executor(cfg.database.url)
    try:
        await ex.run("SELECT 1")
        conn_ok = True
        readonly_ok = False
        try:
            await ex.run("CREATE TEMP TABLE _veil_probe (x int)")
        except Exception as exc:
            readonly_ok = "read-only" in str(exc).lower() or "cannot execute" in str(exc).lower()
        return conn_ok, readonly_ok
    finally:
        await ex.close()


async def _run_one(cfg: Config, sql: str):
    from .pipeline import Pipeline

    pipeline = Pipeline(cfg)
    try:
        return await pipeline.query(sql)
    finally:
        await pipeline.close()


def _mark(ok: bool) -> str:
    return "[green]PASS[/]" if ok else "[red]FAIL[/]"


def _render_config(db_url: str, rules: list[tuple[str, str, str]], pii_tables: list[str]) -> str:
    lines = [
        "# veil configuration — https://github.com/mathu97/dbveil",
        "database:",
        f"  url: {db_url}",
        "",
        "guard:",
        "  allow_select_star: false   # block SELECT * on PII tables; force explicit columns",
        "  max_rows: 1000",
        "  statement_timeout_ms: 15000",
        "  pii_tables:",
    ]
    if pii_tables:
        lines += [f"    - {t}" for t in pii_tables]
    else:
        lines.append("    []   # tables where SELECT * is always rejected")

    lines += [
        "",
        "redact:",
        "  # Deterministic, always-on regex redaction for structured PII.",
        "  builtin_patterns:",
        "    email: true",
        "    phone: true",
        "    credit_card: true",
        "    ssn: true",
        "    ip: false",
        "  hash_salt: \"\"   # set a stable secret to keep hashed values join-able across runs",
        "  # Column-level rules. strategy: mask | null | hash | partial",
        "  columns:",
    ]
    if rules:
        for col, strategy, _ in rules:
            lines.append(f"    - {{ column: {col}, strategy: {strategy} }}")
    else:
        lines.append("    []   # e.g. - { column: email, strategy: hash }")

    lines += [
        "  # Optional probabilistic NER for free-text PII (names/addresses).",
        "  # Backstop only — never the sole control. Needs: pip install 'dbveil[ner]'",
        "  ner:",
        "    enabled: false",
        "    engine: presidio   # presidio | llm",
        "    entities: [PERSON, LOCATION, EMAIL_ADDRESS, PHONE_NUMBER]",
        "    score_threshold: 0.5",
        "",
        "audit_log: veil-audit.jsonl",
        "",
    ]
    return "\n".join(lines)
