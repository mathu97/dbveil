from __future__ import annotations

import logging

import asyncpg

from .log import mask_dsn
from .resolvers import resolve_url
from .result import ResultSet

log = logging.getLogger(__name__)


class Executor:
    def __init__(self, url_ref: str, statement_timeout_ms: int = 15000, max_rows: int = 1000) -> None:
        self.url_ref = url_ref
        self.statement_timeout_ms = statement_timeout_ms
        self.max_rows = max_rows
        self._dsn: str | None = None
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is None:
            if self._dsn is None:
                self._dsn = resolve_url(self.url_ref)
            log.debug("opening connection pool to %s", mask_dsn(self._dsn))
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=4)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def run(self, sql: str) -> ResultSet:
        sql = sql.strip().rstrip(";").strip()
        await self.connect()
        async with self._pool.acquire() as conn:
            tr = conn.transaction(readonly=True)
            await tr.start()
            try:
                await conn.execute(f"SET LOCAL statement_timeout = {int(self.statement_timeout_ms)}")
                stmt = await conn.prepare(sql)
                columns = [a.name for a in stmt.get_attributes()]
                records = await stmt.fetch()
            finally:
                await tr.rollback()

        truncated = len(records) > self.max_rows
        rows = [list(r) for r in records[: self.max_rows]]
        return ResultSet(columns=columns, rows=rows, truncated=truncated, row_count=len(rows))

    async def _fetch_meta(self, sql: str, *args) -> ResultSet:
        await self.connect()
        async with self._pool.acquire() as conn:
            tr = conn.transaction(readonly=True)
            await tr.start()
            try:
                stmt = await conn.prepare(sql)
                columns = [a.name for a in stmt.get_attributes()]
                records = await stmt.fetch(*args)
            finally:
                await tr.rollback()
        rows = [list(r) for r in records]
        return ResultSet(columns=columns, rows=rows, row_count=len(rows))

    async def list_tables(self) -> ResultSet:
        return await self._fetch_meta(
            "SELECT table_schema, table_name "
            "FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_schema, table_name"
        )

    async def describe(self, table: str) -> ResultSet:
        if "." in table:
            schema, name = table.split(".", 1)
        else:
            schema, name = "public", table
        return await self._fetch_meta(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = $1 AND table_name = $2 "
            "ORDER BY ordinal_position",
            schema,
            name,
        )
