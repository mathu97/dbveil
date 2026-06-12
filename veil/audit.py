from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def record(self, sql: str, outcome) -> None:
        if outcome.blocked_reason:
            status = "blocked"
        elif outcome.error:
            status = "error"
        else:
            status = "allowed"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "database": outcome.database,
            "status": status,
            "sql": sql.strip()[:2000],
            "reason": outcome.blocked_reason,
            "error": outcome.error,
            "rows": outcome.row_count,
            "redactions": outcome.redactions,
            "truncated": outcome.truncated,
            "duration_ms": round(outcome.duration_ms, 1),
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
