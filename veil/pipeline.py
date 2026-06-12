from __future__ import annotations

import time
from dataclasses import dataclass, field

from .audit import AuditLog
from .config import Config
from .executor import Executor
from .guard import check_query
from .redact import Redactor


@dataclass
class QueryOutcome:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    redactions: int = 0
    blocked_reason: str | None = None
    error: str | None = None
    duration_ms: float = 0.0


class Pipeline:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.executor = Executor(
            config.database.url,
            config.guard.statement_timeout_ms,
            config.guard.max_rows,
        )
        self.redactor = Redactor(config.redact)
        self.audit = AuditLog(config.audit_log)

    async def query(self, sql: str) -> QueryOutcome:
        start = time.perf_counter()

        verdict = check_query(
            sql,
            allow_select_star=self.config.guard.allow_select_star,
            pii_tables=self.config.guard.pii_tables,
        )
        if not verdict.allowed:
            outcome = QueryOutcome(
                ok=False,
                blocked_reason=verdict.reason,
                duration_ms=_ms(start),
            )
            self.audit.record(sql, outcome)
            return outcome

        try:
            rs = await self.executor.run(sql)
        except Exception as exc:
            outcome = QueryOutcome(ok=False, error=str(exc), duration_ms=_ms(start))
            self.audit.record(sql, outcome)
            return outcome

        redactions = self.redactor.apply(rs)
        outcome = QueryOutcome(
            ok=True,
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
