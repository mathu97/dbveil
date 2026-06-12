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
from .resolvers import describe_ref

app = typer.Typer(
    add_completion=False,
    help="veil — a local read-only, PII-redacting proxy for safe AI database access.",
)
console = Console()
err = Console(stderr=True)


@app.callback()
def _main(
    debug: bool = typer.Option(
        False, "--debug", help="Print debug logs to stderr (or set VEIL_DEBUG=1)."
    ),
) -> None:
    from .log import configure

    configure(debug)

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
    """Create a veil.yaml — interactively pick each database's secret source."""
    path = Config.default_path()
    if path.exists() and not force:
        err.print(f"[yellow]{path} already exists. Use --force to overwrite.[/]")
        raise typer.Exit(1)

    console.print(Panel.fit("[bold]veil init[/] — let's set up safe database access", border_style="cyan"))

    instances: dict[str, str] = {}
    while True:
        default_name = "default" if not instances else f"db{len(instances) + 1}"
        name = _text("Database name", default=default_name)
        if not name:
            name = default_name
        if name in instances:
            err.print(f"[yellow]'{name}' is already added — pick another name.[/]")
            continue
        url = _choose_source(name)
        if not url:
            continue
        instances[name] = url
        if not _confirm("Add another database?", default=False):
            break

    if len(instances) == 1:
        default = next(iter(instances))
    else:
        default = _select("Which database is the default?", list(instances))

    rules: list[tuple[str, str, str]] = []
    pii_tables: list[str] = []
    if _confirm(f"Introspect '{default}' now to auto-suggest PII columns?", default=False):
        try:
            rules, pii_tables = asyncio.run(_introspect(_resolve_env(instances[default])))
            console.print(f"[green]Found {len(rules)} likely PII column(s) across {len(pii_tables)} table(s).[/]")
        except Exception as exc:
            err.print(f"[yellow]Introspection failed ({exc}). Writing a template you can edit by hand.[/]")

    path.write_text(_render_config(instances, default, rules, pii_tables))
    console.print(f"[bold green]Wrote {path}[/]")
    console.print("Next: [cyan]veil doctor[/] to verify, then [cyan]veil up[/] to run the proxy.")


def _choose_source(name: str) -> str | None:
    from InquirerPy.base.control import Choice

    choice = _select(
        f"How should veil get the connection string for {name}?",
        [
            Choice("op", "1Password — browse and pick a secret (op://)"),
            Choice("paste", "Paste a value — a postgresql:// URL or an op:// / env:// reference"),
            Choice("env", "Environment variable — env://VAR"),
        ],
    )
    if choice == "op":
        return _pick_onepassword()
    if choice == "env":
        return f"env://{_text('Environment variable name', default='VEIL_DATABASE_URL')}"
    return _text("Connection string or reference")


def _pick_onepassword() -> str | None:
    from . import onepassword as op

    try:
        op.ensure_installed()
    except op.OpError as exc:
        err.print(f"[red]1Password unavailable:[/]\n{exc}")
        return _manual_op_ref()

    account = None
    accounts = op.list_accounts()
    if len(accounts) == 1:
        account = accounts[0][1]
    elif len(accounts) > 1:
        by_label = {label: ref for label, ref in accounts}
        label = _fuzzy("Pick a 1Password account", list(by_label))
        account = by_label[label]

    try:
        op.ensure_signed_in(account)
    except op.OpError as exc:
        err.print(f"[red]1Password:[/]\n{exc}")
        return _manual_op_ref()

    try:
        vault = _fuzzy("Pick a vault", op.list_vaults(account))
        items = op.list_items(vault, account)
        if not items:
            err.print("[yellow]no items in that vault[/]")
            return _manual_op_ref()
        item = _fuzzy("Pick the item with the connection string", items)
        fields = op.list_fields(vault, item, account)
        if not fields:
            err.print("[yellow]no fields on that item[/]")
            return _manual_op_ref()
        field = _fuzzy("Pick the field with the DSN", fields)
    except op.OpError as exc:
        err.print(f"[red]1Password error:[/] {exc}")
        return _manual_op_ref()

    ref = f"op://{vault}/{item}/{field}"
    console.print(f"[green]Using[/] {ref}")
    return ref


def _manual_op_ref() -> str | None:
    if _confirm("Paste an op:// reference manually instead?", default=True):
        return _text("op:// reference")
    return None


def _text(message: str, default: str | None = None) -> str:
    from . import prompts

    return prompts.text(message, default)


def _confirm(message: str, default: bool = False) -> bool:
    from . import prompts

    return prompts.confirm(message, default)


def _select(message: str, choices, default=None):
    from . import prompts

    return prompts.select(message, choices, default)


def _fuzzy(message: str, choices) -> str:
    from . import prompts

    return prompts.fuzzy(message, choices)


@app.command()
def doctor(
    config: str = typer.Option(None, "--config", "-c", help="Path to veil.yaml."),
    db: str = typer.Option(None, "--db", "-d", help="Which database instance to probe (default: configured default)."),
) -> None:
    """Verify the guard, database connectivity, and read-only enforcement."""
    cfg = _load(config)
    try:
        view = cfg.instance(db)
    except KeyError as exc:
        err.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    table = Table(title=f"veil doctor · {view.name}", show_header=True, header_style="bold")
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
        conn_ok, readonly_ok = asyncio.run(_probe(view))
    except Exception as exc:
        detail = str(exc)

    table.add_row(
        f"connection to '{view.name}' (via {describe_ref(view.url)})",
        _mark(conn_ok) + (f"  [dim]{detail}[/]" if detail else ""),
    )
    table.add_row("server-side READ ONLY transaction rejects writes", _mark(readonly_ok))

    console.print(table)
    if not (guard_ok and conn_ok and readonly_ok):
        raise typer.Exit(1)


@app.command(name="test-query")
def test_query(
    sql: str = typer.Argument(..., help="A read-only SQL query to run through veil."),
    config: str = typer.Option(None, "--config", "-c"),
    db: str = typer.Option(None, "--db", "-d", help="Which database instance to query (default: configured default)."),
) -> None:
    """Run one query through the full guard + redact pipeline and print the result."""
    cfg = _load(config)
    try:
        outcome = asyncio.run(_run_one(cfg, sql, db))
    except KeyError as exc:
        err.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

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
    names = cfg.instance_names()
    err.print(
        f"[bold green]veil[/] up · stdio · guard=read-only · "
        f"databases={', '.join(names)} (default: {cfg.default}) · audit→{cfg.audit_log}"
    )
    from .mcp_server import build_server

    build_server(cfg).run()


@app.command()
def instances(
    config: str = typer.Option(None, "--config", "-c"),
) -> None:
    """List configured database instances and how each DSN is resolved."""
    cfg = _load(config)
    table = Table(title="veil databases", show_header=True, header_style="bold")
    table.add_column("name")
    table.add_column("source")
    table.add_column("reference")
    table.add_column("default", justify="center")
    for name in cfg.instance_names():
        view = cfg.instance(name)
        table.add_row(
            name,
            describe_ref(view.url),
            _safe_ref(view.url),
            "●" if name == cfg.default else "",
        )
    console.print(table)


@app.command()
def monitor(
    config: str = typer.Option(None, "--config", "-c"),
) -> None:
    """Live view of the audit log (allowed / blocked / redactions). Ctrl-C to quit."""
    cfg = _load(config)
    from .tui import run_monitor

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


async def _probe(view) -> tuple[bool, bool]:
    ex = Executor(view.url)
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


async def _run_one(cfg: Config, sql: str, db: str | None = None):
    from .engine import Veil

    veil = Veil(cfg)
    try:
        return await veil.query(sql, db)
    finally:
        await veil.close()


def _mark(ok: bool) -> str:
    return "[green]PASS[/]" if ok else "[red]FAIL[/]"


def _safe_ref(ref: str) -> str:
    scheme = ref.split("://", 1)[0].lower() if "://" in ref else ""
    if scheme in ("op", "env", "gcp"):
        return ref
    return re.sub(r"(://[^:/@]+:)[^@]+(@)", r"\1***\2", ref)


def _render_config(
    instances: dict[str, str],
    default: str,
    rules: list[tuple[str, str, str]],
    pii_tables: list[str],
) -> str:
    lines = ["# veil configuration — https://github.com/mathu97/dbveil", ""]
    if len(instances) == 1 and "default" in instances:
        lines += ["database:", f"  url: {instances['default']}", ""]
    else:
        lines.append("databases:")
        for name, url in instances.items():
            lines += [f"  {name}:", f"    url: {url}"]
        lines += [f"default: {default}", ""]

    lines += [
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
