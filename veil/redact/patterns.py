from __future__ import annotations

import re

from ..config import BuiltinPatterns

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PHONE = re.compile(
    r"(?<!\d)(?:\+?\d{1,2}[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)"
)
CC = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn(candidate: str) -> bool:
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def redact_text(text: str, patterns: BuiltinPatterns) -> tuple[str, int]:
    count = 0

    if patterns.email:
        text, n = EMAIL.subn("[email]", text)
        count += n
    if patterns.ssn:
        text, n = SSN.subn("[ssn]", text)
        count += n
    if patterns.credit_card:
        hits = 0

        def _cc(m):
            nonlocal hits
            if _luhn(m.group(0)):
                hits += 1
                return "[card]"
            return m.group(0)

        text = CC.sub(_cc, text)
        count += hits
    if patterns.phone:
        text, n = PHONE.subn("[phone]", text)
        count += n
    if patterns.ip:
        text, n = IPV4.subn("[ip]", text)
        count += n

    return text, count
