from __future__ import annotations

import json
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header

_COLORS = {"allowed": "green", "blocked": "red", "error": "yellow"}


class MonitorApp(App):
    TITLE = "veil monitor"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = Path(path)
        self._offset = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("time", "status", "rows", "redactions", "ms", "query")
        self.set_interval(1.0, self._poll)
        self._poll()

    def _poll(self) -> None:
        if not self.path.exists():
            return
        with self.path.open() as f:
            f.seek(self._offset)
            chunk = f.read()
            self._offset = f.tell()

        table = self.query_one(DataTable)
        for line in chunk.splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            status = e.get("status", "?")
            table.add_row(
                (e.get("ts", "") or "")[11:19],
                Text(status, style=_COLORS.get(status, "white")),
                str(e.get("rows", "")),
                str(e.get("redactions", "")),
                str(e.get("duration_ms", "")),
                (e.get("sql", "") or "").replace("\n", " ")[:90],
            )
        try:
            table.scroll_end(animate=False)
        except Exception:
            pass


def run_monitor(path: str) -> None:
    MonitorApp(path).run()
