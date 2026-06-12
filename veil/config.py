from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


class RedactStrategy(str, Enum):
    MASK = "mask"
    NULL = "null"
    HASH = "hash"
    PARTIAL = "partial"


class ColumnRule(BaseModel):
    column: str
    strategy: RedactStrategy = RedactStrategy.MASK
    keep: int = 4


class BuiltinPatterns(BaseModel):
    email: bool = True
    phone: bool = True
    credit_card: bool = True
    ssn: bool = True
    ip: bool = False


class NerConfig(BaseModel):
    enabled: bool = False
    engine: str = "presidio"
    entities: list[str] = Field(
        default_factory=lambda: ["PERSON", "LOCATION", "EMAIL_ADDRESS", "PHONE_NUMBER"]
    )
    score_threshold: float = 0.5
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"


class RedactConfig(BaseModel):
    columns: list[ColumnRule] = Field(default_factory=list)
    builtin_patterns: BuiltinPatterns = Field(default_factory=BuiltinPatterns)
    ner: NerConfig = Field(default_factory=NerConfig)
    hash_salt: str = ""


class GuardConfig(BaseModel):
    allow_select_star: bool = False
    pii_tables: list[str] = Field(default_factory=list)
    max_rows: int = 1000
    statement_timeout_ms: int = 15000


class DatabaseConfig(BaseModel):
    url: str


class InstanceConfig(BaseModel):
    url: str
    guard: GuardConfig | None = None
    redact: RedactConfig | None = None


@dataclass
class InstanceView:
    name: str
    url: str
    guard: GuardConfig
    redact: RedactConfig


class Config(BaseModel):
    database: DatabaseConfig | None = None
    databases: dict[str, InstanceConfig] = Field(default_factory=dict)
    default: str | None = None
    guard: GuardConfig = Field(default_factory=GuardConfig)
    redact: RedactConfig = Field(default_factory=RedactConfig)
    audit_log: str = "veil-audit.jsonl"

    @model_validator(mode="after")
    def _normalize(self) -> "Config":
        if not self.databases:
            if self.database is not None:
                self.databases = {"default": InstanceConfig(url=self.database.url)}
            else:
                raise ValueError("config must define either `database.url` or a `databases:` map")

        if self.default is None:
            if "default" in self.databases:
                self.default = "default"
            elif len(self.databases) == 1:
                self.default = next(iter(self.databases))
            else:
                raise ValueError(
                    "multiple databases configured — set `default:` to one of: "
                    + ", ".join(self.databases)
                )

        if self.default not in self.databases:
            raise ValueError(
                f"`default: {self.default}` is not one of the configured databases: "
                + ", ".join(self.databases)
            )
        return self

    def instance(self, name: str | None = None) -> InstanceView:
        name = name or self.default
        if name not in self.databases:
            raise KeyError(
                f"unknown database {name!r}. configured: {', '.join(self.databases)}"
            )
        inst = self.databases[name]
        return InstanceView(
            name=name,
            url=inst.url,
            guard=inst.guard or self.guard,
            redact=inst.redact or self.redact,
        )

    def instance_names(self) -> list[str]:
        return list(self.databases)

    @classmethod
    def default_path(cls) -> Path:
        return Path(os.environ.get("VEIL_CONFIG", "veil.yaml"))

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        path = Path(path) if path else cls.default_path()
        if not path.exists():
            raise FileNotFoundError(
                f"config not found at {path}. Run `veil init` to create one."
            )
        data = yaml.safe_load(path.read_text()) or {}
        _expand_env(data)
        cfg = cls(**data)
        logging.getLogger(__name__).debug(
            "loaded config from %s; databases=%s default=%s",
            path,
            ", ".join(cfg.instance_names()),
            cfg.default,
        )
        return cfg

    def dump_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)


def _expand_env(node):
    if isinstance(node, dict):
        for k, v in node.items():
            node[k] = _expand_env(v)
        return node
    if isinstance(node, list):
        return [_expand_env(v) for v in node]
    if isinstance(node, str):
        def repl(m):
            return os.environ.get(m.group(1), m.group(0))

        return _ENV_PATTERN.sub(repl, node)
    return node
