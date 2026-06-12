from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .config import Config
from .pipeline import Pipeline, QueryOutcome
from .serialize import to_jsonable


def build_server(config: Config) -> FastMCP:
    mcp = FastMCP("veil")
    pipeline = Pipeline(config)

    @mcp.tool()
    async def query(sql: str) -> str:
        """Run a single read-only SQL query against the database.

        Only SELECT / SHOW / EXPLAIN are permitted; any write or DDL is rejected
        before execution. PII in the results is redacted before they reach you.
        """
        return _format(await pipeline.query(sql))

    @mcp.tool()
    async def list_tables() -> str:
        """List the tables available to query, schema-qualified."""
        rs = await pipeline.executor.list_tables()
        return json.dumps({"columns": rs.columns, "rows": to_jsonable(rs.rows)})

    @mcp.tool()
    async def describe_table(table: str) -> str:
        """Show column names and types for a table. Accepts 'schema.table' or 'table'."""
        rs = await pipeline.executor.describe(table)
        return json.dumps({"columns": rs.columns, "rows": to_jsonable(rs.rows)})

    return mcp


def _format(outcome: QueryOutcome) -> str:
    if outcome.blocked_reason:
        return json.dumps({"status": "blocked", "reason": outcome.blocked_reason})
    if outcome.error:
        return json.dumps({"status": "error", "error": outcome.error})

    payload = {
        "status": "ok",
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
