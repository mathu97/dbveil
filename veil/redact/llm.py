from __future__ import annotations

from ..config import NerConfig

_PROMPT = (
    "You are a strict PII redactor. Replace every piece of personally identifiable "
    "information (names, addresses, emails, phone numbers, government IDs) in the text "
    "below with a bracketed placeholder like [name] or [address]. Output ONLY the "
    "redacted text, nothing else. If unsure whether something is PII, redact it.\n\n"
    "TEXT:\n{text}"
)


class LlmRedactor:
    """Optional local-LLM redaction via Ollama. Experimental and probabilistic.

    Fails closed: if the model is unreachable or errors, the cell is fully masked
    rather than passed through unredacted.
    """

    def __init__(self, cfg: NerConfig) -> None:
        try:
            import httpx  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "httpx not installed. Install the LLM extra: pip install 'dbveil[llm]'"
            ) from exc
        self.cfg = cfg

    def redact(self, text: str) -> tuple[str, int]:
        import httpx

        try:
            resp = httpx.post(
                f"{self.cfg.ollama_url}/api/generate",
                json={
                    "model": self.cfg.ollama_model,
                    "prompt": _PROMPT.format(text=text),
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=30,
            )
            resp.raise_for_status()
            redacted = resp.json().get("response", "").strip()
            if not redacted:
                return "[redacted]", 1
            return redacted, (1 if redacted != text else 0)
        except Exception:
            return "[redacted]", 1
