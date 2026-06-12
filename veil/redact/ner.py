from __future__ import annotations

from ..config import NerConfig


class PresidioRedactor:
    """Optional NER-based redaction for free-text PII (names, addresses).

    Probabilistic: it can miss entities. Use only as a backstop on top of
    deterministic column rules and pattern redaction, never as the sole control.
    """

    def __init__(self, cfg: NerConfig) -> None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
        except ImportError as exc:
            raise RuntimeError(
                "Presidio not installed. Install the NER extra: pip install 'dbveil[ner]'"
            ) from exc

        self.cfg = cfg
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

    def redact(self, text: str) -> tuple[str, int]:
        results = self.analyzer.analyze(
            text=text,
            entities=self.cfg.entities or None,
            language="en",
            score_threshold=self.cfg.score_threshold,
        )
        if not results:
            return text, 0
        anonymized = self.anonymizer.anonymize(text=text, analyzer_results=results)
        return anonymized.text, len(results)
