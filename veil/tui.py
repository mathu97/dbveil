from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

_COLORS = {"allowed": "green", "blocked": "red", "error": "yellow"}


def _render(entries, path: Path):
    table = Table(
        title=f"Tailing {path}  (Ctrl-C to quit)",
        expand=True,
        header_style="bold",
    )
    table.add_column("time")
    table.add_column("status")
    table.add_column("rows", justify="right")
    table.add_column("redactions", justify="right")
    table.add_column("ms", justify="right")
    table.add_column("query", overflow="fold")
    for e in entries:
        status = e.get("status", "?")
        table.add_row(
            (e.get("ts", "") or "")[11:19],
            Text(status, style=_COLORS.get(status, "white")),
            str(e.get("rows", "")),
            str(e.get("redactions", "")),
            str(e.get("duration_ms", "")),
            (e.get("sql", "") or "").replace("\n", " ")[:120],
        )
    return table


def run_monitor(path: str, limit: int = 30) -> None:
    p = Path(path)
    entries: deque = deque(maxlen=limit)
    offset = 0
    console = Console()

    with Live(_render(entries, p), console=console, refresh_per_second=4, screen=False) as live:
        try:
            while True:
                if p.exists():
                    with p.open() as f:
                        f.seek(offset)
                        chunk = f.read()
                        offset = f.tell()
                    for line in chunk.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                    live.update(_render(entries, p))
                else:
                    live.update(Text(f"waiting for audit log at {p} …", style="dim"))
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
