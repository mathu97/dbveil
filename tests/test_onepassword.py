import pytest

from veil import onepassword as op


def test_version_parse(monkeypatch):
    monkeypatch.setattr(op.shutil, "which", lambda _: "/usr/local/bin/op")

    class _P:
        stdout = "2.34.1\n"

    monkeypatch.setattr(op.subprocess, "run", lambda *a, **k: _P())
    assert op.installed_version() == (2, 34, 1)


def test_version_none_when_missing(monkeypatch):
    monkeypatch.setattr(op.shutil, "which", lambda _: None)
    assert op.installed_version() is None


def test_ensure_ready_not_installed(monkeypatch):
    monkeypatch.setattr(op, "installed_version", lambda: None)
    with pytest.raises(op.OpError) as exc:
        op.ensure_ready()
    assert "Install" in str(exc.value)


def test_ensure_ready_too_old(monkeypatch):
    monkeypatch.setattr(op, "installed_version", lambda: (1, 9, 0))
    with pytest.raises(op.OpError) as exc:
        op.ensure_ready()
    assert "too old" in str(exc.value)
