import pytest
from pydantic import ValidationError

from veil.config import Config, RedactStrategy


def test_legacy_single_database():
    cfg = Config(database={"url": "postgresql://a@b/c"})
    assert cfg.default == "default"
    assert cfg.instance_names() == ["default"]
    assert cfg.instance().url == "postgresql://a@b/c"


def test_named_instances_with_default():
    cfg = Config(
        databases={
            "staging": {"url": "op://V/staging/dsn"},
            "prod": {"url": "op://V/prod/dsn"},
        },
        default="prod",
    )
    assert set(cfg.instance_names()) == {"staging", "prod"}
    assert cfg.instance().name == "prod"
    assert cfg.instance("staging").url == "op://V/staging/dsn"


def test_single_named_instance_infers_default():
    cfg = Config(databases={"only": {"url": "env://X"}})
    assert cfg.default == "only"


def test_multiple_without_default_errors():
    with pytest.raises(ValidationError):
        Config(databases={"a": {"url": "env://A"}, "b": {"url": "env://B"}})


def test_default_not_in_databases_errors():
    with pytest.raises(ValidationError):
        Config(databases={"a": {"url": "env://A"}}, default="nope")


def test_no_database_errors():
    with pytest.raises(ValidationError):
        Config()


def test_unknown_instance_raises_keyerror():
    cfg = Config(database={"url": "postgresql://a@b/c"})
    with pytest.raises(KeyError):
        cfg.instance("prod")


def test_per_instance_overrides_shared():
    cfg = Config(
        databases={
            "staging": {"url": "env://S"},
            "prod": {"url": "env://P", "guard": {"max_rows": 50}},
        },
        default="staging",
        guard={"max_rows": 1000},
        redact={"columns": [{"column": "email", "strategy": "hash"}]},
    )
    # prod overrides guard, inherits shared redact
    assert cfg.instance("prod").guard.max_rows == 50
    assert cfg.instance("prod").redact.columns[0].strategy == RedactStrategy.HASH
    # staging inherits shared guard
    assert cfg.instance("staging").guard.max_rows == 1000
