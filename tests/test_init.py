from typer.testing import CliRunner

from veil.cli import app

runner = CliRunner()


def test_init_paste_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    # name=default(enter), source=2 (paste), url, add-another=no, introspect=no
    result = runner.invoke(app, ["init"], input="\n2\npostgresql://u@h/db\nn\nn\n")
    assert result.exit_code == 0, result.output
    cfg = (tmp_path / "veil.yaml").read_text()
    assert "database:" in cfg
    assert "url: postgresql://u@h/db" in cfg


def test_init_env_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    # name=default(enter), source=3 (env), var name(enter -> default), add-another=no, introspect=no
    result = runner.invoke(app, ["init"], input="\n3\n\nn\nn\n")
    assert result.exit_code == 0, result.output
    cfg = (tmp_path / "veil.yaml").read_text()
    assert "url: env://VEIL_DATABASE_URL" in cfg


def test_init_multi_instance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VEIL_CONFIG", raising=False)
    # staging: name, source=2, url; add-another=yes; prod: name, source=2, url; add-another=no;
    # default pick=2 (prod); introspect=no
    result = runner.invoke(
        app,
        ["init"],
        input="staging\n2\npostgresql://s@h/db\ny\nprod\n2\npostgresql://p@h/db\nn\n2\nn\n",
    )
    assert result.exit_code == 0, result.output
    cfg = (tmp_path / "veil.yaml").read_text()
    assert "databases:" in cfg
    assert "staging:" in cfg and "prod:" in cfg
    assert "default: prod" in cfg
