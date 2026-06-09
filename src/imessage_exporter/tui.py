from __future__ import annotations

import datetime
import os
import re
from typing import Callable, Dict, List, Optional

import yaml
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Static


class MessageViewer(App[None]):
    """Interactive iMessage viewer. ← → navigate pages, e exports, q quits."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("left,h", "prev_page", "← Older", show=True),
        Binding("right,l", "next_page", "Newer →", show=True),
        Binding("e", "export", "Export", show=True),
    ]

    CSS = """
    Static#header {
        background: $primary;
        color: $text;
        padding: 0 1;
        height: 1;
    }
    DataTable { height: 1fr; }
    """

    def __init__(
        self,
        messages: List[Dict],
        label: str,
        page_size: int,
        handle_map: Dict[str, str],
        export_fn: Optional[Callable[[], str]] = None,
    ) -> None:
        super().__init__()
        self._messages = messages  # ascending: [0]=oldest, [-1]=newest
        self._label = label
        self._page_size = page_size
        self._handle_map = handle_map
        self._export_fn = export_fn
        self._page = 1

    def compose(self) -> ComposeResult:
        yield Static("", id="header")
        yield DataTable(id="msgs", zebra_stripes=True, show_cursor=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("When", "Sender", "Text")
        self._page = self._total_pages()  # start on newest page
        self._render_page()

    def action_next_page(self) -> None:
        if self._page < self._total_pages():
            self._page += 1
            self._render_page()

    def action_prev_page(self) -> None:
        if self._page > 1:
            self._page -= 1
            self._render_page()

    def action_export(self) -> None:
        if not self._export_fn:
            self.notify("No export configured.", severity="warning")
            return
        try:
            path = self._export_fn()
            self.notify(path, title="Exported", timeout=5)
        except Exception as exc:
            self.notify(str(exc), title="Export failed", severity="error", timeout=5)

    def _render_page(self) -> None:
        self._update_header()
        table = self.query_one(DataTable)
        table.clear()
        for msg in self._cur_messages():
            table.add_row(
                str(msg.get("date") or "N/A"),
                self._fmt_sender(msg),
                Text((msg.get("text") or "").replace("\n", " ")),
            )

    def _update_header(self) -> None:
        hdr = self.query_one("#header", Static)
        hdr.update(
            f" {self._label}  —  page {self._page}/{self._total_pages()}"
            f"  ({len(self._messages)} messages)  [e] export"
        )

    def _cur_messages(self) -> List[Dict]:
        start = (self._page - 1) * self._page_size
        return self._messages[start : start + self._page_size]

    def _total_pages(self) -> int:
        total = len(self._messages)
        if not total:
            return 1
        pages, rem = divmod(total, self._page_size)
        return pages + (1 if rem else 0)

    def _fmt_sender(self, msg: Dict) -> Text:
        if msg.get("from_me"):
            return Text("Me", style="bold green")
        handle = msg.get("handle") or ""
        name = self._handle_map.get(handle) or handle or "Unknown"
        return Text(name, style="bold cyan")


def _build_export_fn(messages: List[Dict], label: str) -> Callable[[], str]:
    def _write() -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "messages"
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(os.getcwd(), f"imessage-{slug}-{ts}.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(
                {"label": label, "exported_at": ts, "messages": messages},
                fh,
                sort_keys=False,
                allow_unicode=True,
            )
        return path
    return _write


def run_viewer(
    messages: List[Dict],
    label: str,
    page_size: int,
    handle_map: Optional[Dict[str, str]] = None,
) -> None:
    """Launch the TUI. messages must be ascending (oldest first)."""
    MessageViewer(
        messages=messages,
        label=label,
        page_size=page_size,
        handle_map=handle_map or {},
        export_fn=_build_export_fn(messages, label),
    ).run()
