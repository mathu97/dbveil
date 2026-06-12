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
    monkeypatch.setattr(resolvers.shutil, "which", lambda _: None)
    with pytest.raises(ResolverError) as exc:
        resolve_url("op://Vault/item/field")
    assert "1Password CLI" in str(exc.value)


def test_onepassword_reads_secret(monkeypatch):
    monkeypatch.setattr(resolvers.shutil, "which", lambda _: "/usr/local/bin/op")

    class _Proc:
        returncode = 0
        stdout = "postgresql://op@host/db\n"
        stderr = ""

    monkeypatch.setattr(resolvers.subprocess, "run", lambda *a, **k: _Proc())
    assert resolve_url("op://Vault/item/field") == "postgresql://op@host/db"


def test_onepassword_signin_hint(monkeypatch):
    monkeypatch.setattr(resolvers.shutil, "which", lambda _: "/usr/local/bin/op")

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "you are not currently signed in"

    monkeypatch.setattr(resolvers.subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(ResolverError) as exc:
        resolve_url("op://Vault/item/field")
    assert "op signin" in str(exc.value)
