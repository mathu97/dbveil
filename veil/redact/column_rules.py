from __future__ import annotations

import hashlib

from ..config import ColumnRule, RedactStrategy


def apply_column_rules(
    columns: list[str],
    rows: list[list],
    rules: list[ColumnRule],
    salt: str = "",
) -> int:
    if not rules:
        return 0

    by_name = {r.column.lower(): r for r in rules}
    targets = {i: by_name[col.lower()] for i, col in enumerate(columns) if col.lower() in by_name}
    if not targets:
        return 0

    count = 0
    for row in rows:
        for i, rule in targets.items():
            if row[i] is None:
                continue
            row[i] = _apply(rule, row[i], salt)
            count += 1
    return count


def _apply(rule: ColumnRule, value, salt: str):
    if rule.strategy == RedactStrategy.NULL:
        return None
    if rule.strategy == RedactStrategy.MASK:
        return "[redacted]"

    text = str(value)
    if rule.strategy == RedactStrategy.HASH:
        digest = hashlib.sha256((salt + text).encode()).hexdigest()[:12]
        return f"sha256:{digest}"
    if rule.strategy == RedactStrategy.PARTIAL:
        keep = max(0, rule.keep)
        if len(text) <= keep:
            return "*" * len(text)
        return "*" * (len(text) - keep) + text[-keep:]
    return value
