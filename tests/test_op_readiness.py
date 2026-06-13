import pytest
from typer.testing import CliRunner

from veil import onepassword as op
from veil.cli import app

runner = CliRunner()


def test_readiness_not_installed(monkeypatch):
    monkeypatch.setattr(op, "installed_version", lambda: None)
    status, hint = op.readiness()
    assert status == "install" and "Install" in hint


def test_readiness_too_old(monkeypatch):
    monkeypatch.setattr(op, "installed_version", lambda: (1, 9, 0))
    status, _ = op.readiness()
    assert status == "install"


def test_readiness_no_accounts(monkeypatch):
    monkeypatch.setattr(op, "installed_version", lambda: (2, 34, 1))
    monkeypatch.setattr(op, "list_accounts", lambda: [])
    status, hint = op.readiness()
    assert status == "signin"
    assert "Integrate with 1Password CLI" in hint


def test_readiness_ready(monkeypatch):
    monkeypatch.setattr(op, "installed_version", lambda: (2, 34, 1))
    monkeypatch.setattr(op, "list_accounts", lambda: [("me (x)", "x")])
    status, hint = op.readiness()
    assert status == "ready" and hint == ""


def test_read_success(monkeypatch):
    monkeypatch.setattr(op, "installed_version", lambda: (2, 34, 1))
    monkeypatch.setattr(op, "_op", lambda *a, **k: "postgresql://x@h/db\n")
    assert op.read("op://V/i/f") == "postgresql://x@h/db"


def test_read_not_signed_in_gives_setup_hint(monkeypatch):
    monkeypatch.setattr(op, "installed_version", lambda: (2, 34, 1))

    def boom(*a, **k):
        raise op.OpError("you are not currently signed in")

    monkeypatch.setattr(op, "_op", boom)
    with pytest.raises(op.OpError) as exc:
        op.read("op://V/i/f")
    assert "Integrate with 1Password CLI" in str(exc.value)


def test_setup_warns_when_op_not_ready(tmp_path, monkeypatch):
    (tmp_path / "veil.yaml").write_text("database:\n  url: op://V/i/f\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    monkeypatch.setattr(op, "readiness", lambda: ("signin", "ENABLE-INTEGRATION-HINT"))
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    assert "ENABLE-INTEGRATION-HINT" in result.output


def test_setup_quiet_without_op(tmp_path, monkeypatch):
    (tmp_path / "veil.yaml").write_text("database:\n  url: postgresql://a@h/db\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
