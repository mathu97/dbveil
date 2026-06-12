from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .audit import AuditLog
from .config import InstanceView
from .executor import Executor
from .guard import check_query
from .redact import Redactor

log = logging.getLogger(__name__)


@dataclass
class QueryOutcome:
    ok: bool
    database: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    redactions: int = 0
    blocked_reason: str | None = None
    error: str | None = None
    duration_ms: float = 0.0


class Pipeline:
    def __init__(self, view: InstanceView, audit: AuditLog) -> None:
        self.view = view
        self.executor = Executor(
            view.url,
            view.guard.statement_timeout_ms,
            view.guard.max_rows,
        )
        self.redactor = Redactor(view.redact)
        self.audit = audit

    async def query(self, sql: str) -> QueryOutcome:
        start = time.perf_counter()
        db = self.view.name
        log.debug("[%s] query: %s", db, sql.strip().replace("\n", " ")[:200])

        verdict = check_query(
            sql,
            allow_select_star=self.view.guard.allow_select_star,
            pii_tables=self.view.guard.pii_tables,
        )
        if not verdict.allowed:
            log.debug("[%s] guard BLOCKED: %s", db, verdict.reason)
            outcome = QueryOutcome(
                ok=False, database=db, blocked_reason=verdict.reason, duration_ms=_ms(start)
            )
            self.audit.record(sql, outcome)
            return outcome
        log.debug("[%s] guard allowed", db)

        try:
            rs = await self.executor.run(sql)
        except Exception as exc:
            log.debug("[%s] execution error: %s", db, exc)
            outcome = QueryOutcome(ok=False, database=db, error=str(exc), duration_ms=_ms(start))
            self.audit.record(sql, outcome)
            return outcome

        redactions = self.redactor.apply(rs)
        log.debug("[%s] %d rows, %d redactions, %.0fms", db, rs.row_count, redactions, _ms(start))
        outcome = QueryOutcome(
            ok=True,
            database=db,
            columns=rs.columns,
            rows=rs.rows,
            row_count=rs.row_count,
            truncated=rs.truncated,
            redactions=redactions,
            duration_ms=_ms(start),
        )
        self.audit.record(sql, outcome)
        return outcome

    async def close(self) -> None:
        await self.executor.close()


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000
