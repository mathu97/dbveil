from veil.config import BuiltinPatterns, ColumnRule, RedactConfig, RedactStrategy
from veil.redact import Redactor
from veil.redact.column_rules import apply_column_rules
from veil.redact.patterns import redact_text
from veil.result import ResultSet


def test_column_mask():
    rows = [[1, "alice@example.com"]]
    n = apply_column_rules(["id", "email"], rows, [ColumnRule(column="email")])
    assert rows[0][1] == "[redacted]"
    assert n == 1


def test_column_null():
    rows = [["secret"]]
    apply_column_rules(["x"], rows, [ColumnRule(column="x", strategy=RedactStrategy.NULL)])
    assert rows[0][0] is None


def test_column_hash_is_deterministic():
    rows1 = [["a@b.com"]]
    rows2 = [["a@b.com"]]
    rule = [ColumnRule(column="e", strategy=RedactStrategy.HASH)]
    apply_column_rules(["e"], rows1, rule)
    apply_column_rules(["e"], rows2, rule)
    assert rows1[0][0] == rows2[0][0]
    assert rows1[0][0].startswith("sha256:")


def test_column_partial():
    rows = [["123456789"]]
    apply_column_rules(["ssn"], rows, [ColumnRule(column="ssn", strategy=RedactStrategy.PARTIAL, keep=4)])
    assert rows[0][0].endswith("6789")
    assert rows[0][0].startswith("*")


def test_pattern_email_phone_ssn():
    text, n = redact_text("reach alice@example.com or 415-555-2671, ssn 123-45-6789", BuiltinPatterns())
    assert "[email]" in text and "[phone]" in text and "[ssn]" in text
    assert n == 3


def test_pattern_credit_card_luhn():
    text, n = redact_text("card 4111111111111111 here", BuiltinPatterns())
    assert "[card]" in text and n == 1
    text2, n2 = redact_text("not a card 1234567890123456", BuiltinPatterns())
    assert n2 == 0


def test_pattern_ip_opt_in():
    off, n_off = redact_text("host 10.0.0.1", BuiltinPatterns(ip=False))
    on, n_on = redact_text("host 10.0.0.1", BuiltinPatterns(ip=True))
    assert n_off == 0 and "[ip]" in on


def test_redactor_end_to_end():
    cfg = RedactConfig(columns=[ColumnRule(column="email", strategy=RedactStrategy.HASH)])
    rs = ResultSet(
        columns=["id", "email", "note"],
        rows=[[1, "a@b.com", "call me at 415-555-2671"]],
        row_count=1,
    )
    n = Redactor(cfg).apply(rs)
    assert rs.rows[0][1].startswith("sha256:")
    assert "[phone]" in rs.rows[0][2]
    assert n >= 2
