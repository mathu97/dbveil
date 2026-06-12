from __future__ import annotations

import logging
import os

from rich.console import Console
from rich.logging import RichHandler

_configured = False


def configure(debug: bool = False) -> None:
    """Enable veil debug logging to stderr when --debug or VEIL_DEBUG is set."""
    global _configured
    enabled = debug or os.environ.get("VEIL_DEBUG") not in (None, "", "0", "false", "False")

    logger = logging.getLogger("veil")
    if not _configured:
        handler = RichHandler(
            console=Console(stderr=True),
            show_path=False,
            markup=False,
            rich_tracebacks=True,
        )
        handler.setFormatter(logging.Formatter("%(name)s — %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        _configured = True

    logger.setLevel(logging.DEBUG if enabled else logging.WARNING)


def mask_dsn(dsn: str) -> str:
    """Show a DSN's host without leaking the password (for debug logs)."""
    import re

    m = re.search(r"@([^/:?\s]+)", dsn or "")
    host = m.group(1) if m else "?"
    scheme = dsn.split("://", 1)[0] if "://" in (dsn or "") else "?"
    return f"{scheme}://***@{host}"
