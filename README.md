# veil

**A local read-only, PII-redacting proxy that lets AI agents query your database safely.**

Point Claude Code (or any MCP client) at `veil` instead of your database. Every query is
forced through three deterministic guarantees before a single row reaches the model:

1. **Read-only guard** — the query is parsed with Postgres's real grammar (`libpg_query`).
   Only `SELECT` / `SHOW` / `EXPLAIN` survive. Writes, DDL, multi-statements, data-modifying
   CTEs, `SELECT INTO`, and row locks are rejected *before execution* — not by asking the model
   nicely, by refusing to run them.
2. **PII redaction** — results are scrubbed before they leave your machine: deterministic
   column rules + always-on regex for structured PII (emails, phones, cards, SSNs), with an
   optional NER/LLM backstop for free-text.
3. **Audit** — every query and verdict is appended to a log you can tail live in a TUI.

A guarded chokepoint in front of the DB, shrunk to a single open-source command with zero
infrastructure to stand up.

```
Claude Code ──MCP──▶  veil  ──READ ONLY txn──▶  your database
                       │
                       ├─ guard:   parse → allow SELECT only
                       ├─ redact:  column rules + regex + (optional) NER/LLM
                       └─ audit:   veil-audit.jsonl
```

## Why

You want an agent to act as a data analyst over real tables — "compare what we drafted vs what
was actually sent" — without (a) risking a destructive query or (b) shipping customer PII to a
model provider. Handing an agent raw DB credentials and hoping it only writes `SELECT` is not a
control. `veil` makes the unsafe paths impossible at the layer the agent can't talk its way past.

## Install

```bash
pip install dbveil          # or: uv pip install dbveil
# optional extras:
pip install 'dbveil[ner]'   # Presidio NER backstop for names/addresses
pip install 'dbveil[llm]'   # local-LLM (Ollama) redaction
```

## Quickstart

```bash
veil init          # interactive: DB URL + auto-detect PII columns → writes veil.yaml
veil doctor        # verify guard, connectivity, and that READ ONLY actually blocks writes
veil test-query "SELECT email, created_at FROM users LIMIT 5"   # try it without an agent
veil up            # run the MCP proxy on stdio (what Claude Code connects to)
```

Try a write to see the guard refuse it:

```bash
veil test-query "DELETE FROM users"
# BLOCKED — write or DDL operation detected: DELETE
```

### Connect Claude Code

```bash
claude mcp add veil -- veil up
```

or commit a `.mcp.json` so your whole team gets it:

```json
{
  "mcpServers": {
    "veil": { "command": "veil", "args": ["up"], "env": { "VEIL_CONFIG": "veil.yaml" } }
  }
}
```

Now the agent has these tools — `query`, `list_tables`, `describe_table`, `list_databases` —
and physically cannot write or see raw PII.

## Databases & secret resolution

You never put a DSN (or a secret) directly in the file. Each database's `url` is a *reference*
resolved at connect time, chosen by its scheme:

| Reference | Resolved by |
|---|---|
| `op://vault/item/field` | **1Password** CLI (`op read`) — uses your existing 1Password auth; `OP_SERVICE_ACCOUNT_TOKEN` in CI |
| `env://VAR_NAME` | environment variable |
| `${VAR}` | inline env expansion |
| `gcp://project/secret` | GCP Secret Manager *(coming soon)* |
| `postgresql://…` | a literal DSN |

Configure one or many named instances; the agent picks one per query (`query(sql, database="prod")`),
or the CLI with `--db`:

```yaml
databases:
  staging: { url: "op://Engineering/veil-staging-db/dsn" }
  prod:    { url: "op://Engineering/veil-prod-db/dsn" }
default: staging
```

```bash
veil instances                 # list configured DBs and how each resolves (no secrets read)
veil doctor --db prod          # verify a specific instance
veil test-query --db prod "…"  # query a specific instance
```

A single `database.url:` still works and becomes the lone `default` instance.

### Watch it live

```bash
veil monitor       # TUI tailing veil-audit.jsonl: allowed / blocked / redaction counts
```

## Configuration

`veil init` writes a commented `veil.yaml`. Full reference in
[`examples/veil.example.yaml`](examples/veil.example.yaml). The essentials:

```yaml
database:
  url: ${DATABASE_URL}          # env refs kept out of the file

guard:
  allow_select_star: false      # block SELECT * on PII tables; force explicit columns
  max_rows: 1000
  statement_timeout_ms: 15000
  pii_tables: [contacts, users]

redact:
  builtin_patterns: { email: true, phone: true, credit_card: true, ssn: true, ip: false }
  columns:
    - { column: email,     strategy: hash }      # sha256, still join-able
    - { column: full_name, strategy: mask }      # -> [redacted]
    - { column: ssn,       strategy: partial, keep: 4 }
  ner: { enabled: false, engine: presidio }      # optional backstop
```

## How redaction is layered (and its honest limits)

`veil` defends from the **deterministic** side first, because that's the only kind you can trust
not to leak:

| Layer | What it catches | Deterministic? |
|---|---|---|
| **Column rules** | Known PII columns (`email`, `ssn`, …) by name | ✅ yes |
| **Built-in regex** | Emails, phones, Luhn-valid cards, SSNs, IPs — even aliased or in free-text | ✅ yes |
| **NER (Presidio)** | Names / addresses in free-text the above miss | ⚠️ probabilistic |
| **LLM (Ollama)** | Same, via a local model | ⚠️ probabilistic, experimental |

**Use the probabilistic layers only as a backstop.** ML/NER *will* eventually miss a name or an
oddly-formatted address — that's a leak. For columns you already know are sensitive, the column
rules are the real control. The LLM redactor fails *closed*: if the model errors, the cell is
masked, never passed through.

## Security model

- **Two independent read-only layers.** The parser rejects non-reads, *and* every query runs
  inside a `SET TRANSACTION READ ONLY` transaction — so even a parser gap can't write.
- **Give veil a least-privilege credential.** Best practice is a `GRANT SELECT`-only database
  role (ideally on a read replica). Then "read-only" is enforced by the database itself, and the
  credential `veil` holds is low-blast-radius: a leak exposes already-masked reads and can write
  nothing. `veil doctor` confirms the READ ONLY transaction rejects writes against your DB.
- **PII never leaves your machine unmasked.** Redaction happens in-process, before results are
  serialized to the MCP client.

## Secure connectivity

`veil` connects to whatever DSN you give it, so the network path is yours to choose:

- **Tailscale** — put your DB behind a tailnet and point `database.url` at the tailnet host. No
  public DB port.
- **Short-lived credentials** — `${DATABASE_URL}` is expanded at load, so you can inject an
  ephemeral token (RDS IAM auth, Cloud SQL IAM, a Vault dynamic user) instead of a static
  password.
- **Railway / managed PaaS** — use the provided TLS endpoint with a dedicated read-only role.

## Roadmap

- **Postgres wire-protocol frontend** — so `psql`, BI tools, and any client (not just MCP) get
  the same guard + redaction. The pipeline is already frontend-agnostic.
- **More engines** — MySQL, SQLite (the guard's parser is the only Postgres-specific piece; it's
  a pluggable backend).
- **Schema-aware lineage** — resolve aliased PII columns back to their source table.

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -e '.[dev]'
pytest
```

## License

MIT
