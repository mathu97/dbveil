from typer.testing import CliRunner

import veil.cli as cli
from veil.cli import app

runner = CliRunner()


def test_instances_list(tmp_path, monkeypatch):
    cfg = tmp_path / "veil.yaml"
    cfg.write_text(
        "databases:\n  staging: {url: env://S}\n  prod: {url: 'op://V/p/dsn'}\ndefault: staging\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    result = runner.invoke(app, ["instances", "list"])
    assert result.exit_code == 0, result.output
    assert "staging" in result.output and "prod" in result.output


def test_instances_add_converts_single_to_map(tmp_path, monkeypatch):
    cfg = tmp_path / "veil.yaml"
    cfg.write_text("database:\n  url: postgresql://a@h/db\nguard:\n  max_rows: 50\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    monkeypatch.setattr(cli, "_text", lambda *a, **k: "prod")
    monkeypatch.setattr(cli, "_choose_source", lambda: "op://V/prod/dsn")

    result = runner.invoke(app, ["instances", "add"])
    assert result.exit_code == 0, result.output

    out = cfg.read_text()
    assert "databases:" in out and "database:\n" not in out
    assert "default:" in out
    assert "prod:" in out and "op://V/prod/dsn" in out
    assert "max_rows: 50" in out  # existing config preserved

    # the rewritten config still loads and exposes both instances
    from veil.config import Config

    loaded = Config.load(cfg)
    assert set(loaded.instance_names()) == {"default", "prod"}
    assert loaded.default == "default"


def test_instances_add_to_existing_map(tmp_path, monkeypatch):
    cfg = tmp_path / "veil.yaml"
    cfg.write_text("databases:\n  staging: {url: env://S}\ndefault: staging\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    monkeypatch.setattr(cli, "_text", lambda *a, **k: "prod")
    monkeypatch.setattr(cli, "_choose_source", lambda: "op://V/prod/dsn")

    result = runner.invoke(app, ["instances", "add"])
    assert result.exit_code == 0, result.output

    from veil.config import Config

    loaded = Config.load(cfg)
    assert set(loaded.instance_names()) == {"staging", "prod"}


def test_instances_add_rejects_duplicate(tmp_path, monkeypatch):
    cfg = tmp_path / "veil.yaml"
    cfg.write_text("databases:\n  prod: {url: env://P}\ndefault: prod\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    monkeypatch.setattr(cli, "_text", lambda *a, **k: "prod")
    monkeypatch.setattr(cli, "_choose_source", lambda: "env://X")

    result = runner.invoke(app, ["instances", "add"])
    assert result.exit_code == 1
