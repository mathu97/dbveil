from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .config import Config
from .engine import Veil
from .pipeline import QueryOutcome
from .serialize import to_jsonable


def build_server(config: Config) -> FastMCP:
    mcp = FastMCP("veil")
    veil = Veil(config)

    @mcp.tool()
    async def query(sql: str, database: str | None = None) -> str:
        """Run a single read-only SQL query against a configured database.

        Only SELECT / SHOW / EXPLAIN are permitted; any write or DDL is rejected
        before execution, and PII in the results is redacted before they reach you.
        Pass `database` to choose an instance (call list_databases to see options);
        omit it to use the default.
        """
        try:
            outcome = await veil.query(sql, database)
        except KeyError as exc:
            return json.dumps({"status": "error", "error": str(exc)})
        return _format(outcome)

    @mcp.tool()
    async def list_databases() -> str:
        """List the databases veil can query and which one is the default."""
        return json.dumps({"databases": veil.instance_names(), "default": veil.default})

    @mcp.tool()
    async def list_tables(database: str | None = None) -> str:
        """List the tables available to query (schema-qualified) in a database."""
        try:
            rs = await veil.pipeline(database).executor.list_tables()
        except KeyError as exc:
            return json.dumps({"status": "error", "error": str(exc)})
        return json.dumps({"columns": rs.columns, "rows": to_jsonable(rs.rows)})

    @mcp.tool()
    async def describe_table(table: str, database: str | None = None) -> str:
        """Show column names and types for a table. Accepts 'schema.table' or 'table'."""
        try:
            rs = await veil.pipeline(database).executor.describe(table)
        except KeyError as exc:
            return json.dumps({"status": "error", "error": str(exc)})
        return json.dumps({"columns": rs.columns, "rows": to_jsonable(rs.rows)})

    return mcp


def _format(outcome: QueryOutcome) -> str:
    if outcome.blocked_reason:
        return json.dumps({"status": "blocked", "database": outcome.database, "reason": outcome.blocked_reason})
    if outcome.error:
        return json.dumps({"status": "error", "database": outcome.database, "error": outcome.error})

    payload = {
        "status": "ok",
        "database": outcome.database,
        "columns": outcome.columns,
        "rows": to_jsonable(outcome.rows),
        "row_count": outcome.row_count,
        "truncated": outcome.truncated,
        "redactions": outcome.redactions,
    }
    if outcome.redactions:
        payload["note"] = (
            "PII was redacted by veil. Placeholders such as [email], [phone], "
            "[redacted] or sha256:... are intentional masks, not real values."
        )
    return json.dumps(payload)
