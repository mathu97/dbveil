from __future__ import annotations

from ..config import RedactConfig
from ..result import ResultSet
from .column_rules import apply_column_rules
from .patterns import redact_text


class Redactor:
    def __init__(self, cfg: RedactConfig) -> None:
        self.cfg = cfg
        self._ner = None
        if cfg.ner.enabled:
            if cfg.ner.engine == "presidio":
                from .ner import PresidioRedactor

                self._ner = PresidioRedactor(cfg.ner)
            elif cfg.ner.engine == "llm":
                from .llm import LlmRedactor

                self._ner = LlmRedactor(cfg.ner)
            else:
                raise ValueError(f"unknown ner engine: {cfg.ner.engine}")

    def apply(self, result: ResultSet) -> int:
        count = apply_column_rules(
            result.columns, result.rows, self.cfg.columns, self.cfg.hash_salt
        )
        for row in result.rows:
            for i, value in enumerate(row):
                if not isinstance(value, str) or not value:
                    continue
                new, n = redact_text(value, self.cfg.builtin_patterns)
                if self._ner is not None:
                    new, n2 = self._ner.redact(new)
                    n += n2
                if new != value:
                    row[i] = new
                count += n
        return count


__all__ = ["Redactor"]
