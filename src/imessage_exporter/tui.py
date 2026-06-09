from __future__ import annotations

from typing import Dict, List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Static


class MessageViewer(App[None]):
    """Interactive iMessage conversation viewer with arrow-key page navigation."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("left,h", "prev_page", "← Prev", show=True),
        Binding("right,l", "next_page", "Next →", show=True),
    ]

    CSS = """
    Static#header {
        background: $primary;
        color: $text;
        padding: 0 1;
        height: 1;
    }
    DataTable {
        height: 1fr;
    }
    """

    def __init__(
        self,
        messages: List[Dict],
        label: str,
        page_size: int,
        handle_map: Dict[str, str],
    ) -> None:
        super().__init__()
        self._messages = messages
        self._label = label
        self._page_size = page_size
        self._handle_map = handle_map
        self._page = 1

    def compose(self) -> ComposeResult:
        yield Static("", id="header")
        yield DataTable(id="msgs", zebra_stripes=True, show_cursor=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("When", "Sender", "Text")
        self._render_page()

    def action_next_page(self) -> None:
        if self._page < self._total_pages():
            self._page += 1
            self._render_page()

    def action_prev_page(self) -> None:
        if self._page > 1:
            self._page -= 1
            self._render_page()

    def _render_page(self) -> None:
        self._update_header()
        table = self.query_one(DataTable)
        table.clear()
        for msg in self._cur_messages():
            table.add_row(
                str(msg.get("date") or "N/A"),
                self._sender(msg),
                (msg.get("text") or "").replace("\n", " "),
            )

    def _update_header(self) -> None:
        hdr = self.query_one("#header", Static)
        hdr.update(
            f" {self._label}  —  page {self._page}/{self._total_pages()}"
            f"  ({len(self._messages)} messages total)"
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

    def _sender(self, msg: Dict) -> str:
        handle = msg.get("handle") or ""
        if msg.get("from_me"):
            return "Me"
        return self._handle_map.get(handle) or handle or "Unknown"


def run_viewer(
    messages: List[Dict],
    label: str,
    page_size: int,
    handle_map: Optional[Dict[str, str]] = None,
) -> None:
    """Launch the interactive TUI viewer."""
    MessageViewer(
        messages=messages,
        label=label,
        page_size=page_size,
        handle_map=handle_map or {},
    ).run()
