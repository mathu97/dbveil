from typer.testing import CliRunner

import veil.cli as cli
from veil.cli import app

runner = CliRunner()


def _script(monkeypatch, *, texts=(), selects=(), confirms=(), fuzzies=()):
    ti, si, ci, fi = (iter(texts), iter(selects), iter(confirms), iter(fuzzies))
    monkeypatch.setattr(cli, "_text", lambda *a, **k: next(ti))
    monkeypatch.setattr(cli, "_select", lambda *a, **k: next(si))
    monkeypatch.setattr(cli, "_confirm", lambda *a, **k: next(ci))
    monkeypatch.setattr(cli, "_fuzzy", lambda *a, **k: next(fi))


def test_init_paste_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    _script(
        monkeypatch,
        texts=["default", "postgresql://u@h/db"],
        selects=["paste"],
        confirms=[False, False],  # add another? / introspect?
    )
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    cfg = (tmp_path / "veil.yaml").read_text()
    assert "database:" in cfg
    assert "url: postgresql://u@h/db" in cfg


def test_init_env_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    _script(
        monkeypatch,
        texts=["default", "VEIL_DATABASE_URL"],
        selects=["env"],
        confirms=[False, False],
    )
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    cfg = (tmp_path / "veil.yaml").read_text()
    assert "url: env://VEIL_DATABASE_URL" in cfg


def test_init_multi_instance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    _script(
        monkeypatch,
        texts=["staging", "postgresql://s@h/db", "prod", "postgresql://p@h/db"],
        selects=["paste", "paste", "prod"],  # source, source, default-db
        confirms=[True, False, False],  # add another? yes, no, introspect? no
    )
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    cfg = (tmp_path / "veil.yaml").read_text()
    assert "databases:" in cfg
    assert "staging:" in cfg and "prod:" in cfg
    assert "default: prod" in cfg
