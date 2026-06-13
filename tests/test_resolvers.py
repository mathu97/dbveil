import pytest

from veil import resolvers
from veil.resolvers import (
    EnvResolver,
    LiteralResolver,
    ResolverError,
    describe_ref,
    resolve_url,
)


def test_literal_passthrough():
    dsn = "postgresql://u:p@h:5432/db"
    assert resolve_url(dsn) == dsn
    assert LiteralResolver().resolve(dsn) == dsn


def test_env_resolver(monkeypatch):
    monkeypatch.setenv("MY_DSN", "postgresql://a@b/c")
    assert resolve_url("env://MY_DSN") == "postgresql://a@b/c"


def test_env_resolver_missing(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    with pytest.raises(ResolverError):
        resolve_url("env://NOPE")


def test_empty_ref():
    with pytest.raises(ResolverError):
        resolve_url("   ")


def test_gcp_not_implemented():
    with pytest.raises(ResolverError):
        resolve_url("gcp://proj/secret")


def test_describe_ref():
    assert describe_ref("op://v/i/f") == "1Password"
    assert describe_ref("env://X") == "env"
    assert describe_ref("gcp://p/s") == "GCP Secret Manager"
    assert describe_ref("postgresql://u@h/d") == "literal"


def test_onepassword_missing_cli(monkeypatch):
    from veil import onepassword as op

    monkeypatch.setattr(op, "installed_version", lambda: None)
    with pytest.raises(ResolverError) as exc:
        resolve_url("op://Vault/item/field")
    assert "Install" in str(exc.value)


def test_onepassword_reads_secret(monkeypatch):
    from veil import onepassword as op

    monkeypatch.setattr(op, "read", lambda ref: "postgresql://op@host/db")
    assert resolve_url("op://Vault/item/field") == "postgresql://op@host/db"


def test_onepassword_signin_hint(monkeypatch):
    from veil import onepassword as op

    monkeypatch.setattr(op, "installed_version", lambda: (2, 34, 1))

    def boom(*a, **k):
        raise op.OpError("you are not currently signed in")

    monkeypatch.setattr(op, "_op", boom)
    with pytest.raises(ResolverError) as exc:
        resolve_url("op://Vault/item/field")
    assert "Integrate with 1Password CLI" in str(exc.value)
