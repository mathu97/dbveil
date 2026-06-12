from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResultSet:
    columns: list[str]
    rows: list[list]
    truncated: bool = False
    row_count: int = 0
