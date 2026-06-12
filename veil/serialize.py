from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal


def _value(x):
    if x is None or isinstance(x, (str, int, float, bool)):
        return x
    if isinstance(x, (datetime, date, time)):
        return x.isoformat()
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, uuid.UUID):
        return str(x)
    if isinstance(x, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(x))} bytes>"
    if isinstance(x, (list, tuple)):
        return [_value(i) for i in x]
    if isinstance(x, dict):
        return {k: _value(v) for k, v in x.items()}
    return str(x)


def to_jsonable(rows: list[list]) -> list[list]:
    return [[_value(c) for c in row] for row in rows]
