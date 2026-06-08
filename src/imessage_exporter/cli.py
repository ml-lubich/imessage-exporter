import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .contacts import find_contacts_by_name
from .core import (
    build_export,
    find_chat_by_reference,
    find_chats_by_query,
    find_chats_for_handles,
    list_recent_chats,
    resolve_output_path,
    search_message_rows,
    write_export,
)
from .database import CHAT_DB_PATH, get_db_connection
from .search_index import (
    build_search_index,
    format_index_date,
    index_status,
    search_index,
)
from .utils import cocoa_to_datetime


console = Console()
app = typer.Typer(
    add_completion=False,
    help="Export, search, and browse local iMessage chats.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)
index_app = typer.Typer(
    help="Build and inspect the local all-message search index.",
    rich_markup_mode="rich",
)
app.add_typer(index_app, name="index")

BANNER = [
    " _                                 ",
    "(_)_ __ ___  ___  __ _            ",
    "| | '_ ` _ \\/ __|/ _` |           ",
    "| | | | | | \\__ \\ (_| |           ",
    "|_|_| |_| |_|___/\\__, | export    ",
    "                 |___/            ",
]

GRADIENT = [
    "rgb(255,88,88)",
    "rgb(255,162,67)",
    "rgb(247,220,80)",
    "rgb(76,217,123)",
    "rgb(75,181,255)",
    "rgb(178,128,255)",
]


@dataclass
class Settings:
    db_path: str
    contacts_db_paths: Optional[List[str]]


@app.callback()
def root(
    ctx: typer.Context,
    db_path: str = typer.Option(
        CHAT_DB_PATH,
        "--db-path",
        help="Path to chat.db.",
    ),
    contacts_db_path: Optional[List[str]] = typer.Option(
        None,
        "--contacts-db-path",
        help="Path to a Contacts .abcddb database. Can be used more than once.",
    ),
) -> None:
    """Show the banner and set shared options."""
    _print_banner()
    ctx.obj = Settings(db_path=db_path, contacts_db_paths=contacts_db_path)
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


@app.command("list")
def list_command(
    ctx: typer.Context,
    limit: int = typer.Argument(25, min=1, max=500, help="Number of chats to show."),
) -> None:
    """List recent chats, latest first."""
    conn = _connect(ctx)
    try:
        rows = list_recent_chats(conn, limit)
    finally:
        conn.close()

    table = Table(title=f"Recent chats ({len(rows)})", expand=True)
    table.add_column("ID", style="bold cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Identifier", overflow="fold")
    table.add_column("Messages", justify="right")
    table.add_column("Last activity", no_wrap=True)

    for row in rows:
        table.add_row(
            str(row["ROWID"]),
            row["display_name"] or row["chat_identifier"] or "Unknown",
            row["chat_identifier"] or "",
            str(row["message_count"] or 0),
            _format_date(row["last_msg_date"], "%Y-%m-%d %H:%M"),
        )

    console.print(table)


@app.command("find")
def find_command(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Partial name, phone number, email, or chat ID."),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="Max matches to show."),
) -> None:
    """Find matching contacts and chats."""
    settings = _settings(ctx)
    contacts = find_contacts_by_name(query, settings.contacts_db_paths)
    conn = _connect(ctx)
    try:
        chats = _unique_chats(find_chats_by_query(conn, query, limit))
    finally:
        conn.close()

    if contacts:
        contact_table = Table(title=f"Contacts matching {query!r}", expand=True)
        contact_table.add_column("Name", style="bold")
        contact_table.add_column("Handles", overflow="fold")
        for contact in contacts[:limit]:
            contact_table.add_row(
                str(contact["name"]),
                ", ".join(contact["handles"]) or "No phone/email handles",
            )
        console.print(contact_table)

    if chats:
        chat_table = Table(title=f"Chats matching {query!r}", expand=True)
        chat_table.add_column("ID", style="bold cyan", no_wrap=True)
        chat_table.add_column("Name")
        chat_table.add_column("Identifier", overflow="fold")
        chat_table.add_column("Messages", justify="right")
        chat_table.add_column("Last activity", no_wrap=True)
        for chat in chats:
            chat_table.add_row(
                str(chat["ROWID"]),
                chat["display_name"] or chat["chat_identifier"] or "Unknown",
                chat["chat_identifier"] or "",
                str(chat["message_count"] or 0),
                _format_date(chat["last_msg_date"], "%Y-%m-%d %H:%M"),
            )
        console.print(chat_table)

    if not contacts and not chats:
        console.print(f"[yellow]No contacts or chats found for {query!r}.[/yellow]")
        raise typer.Exit(1)


@app.command("search")
def search_command(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Text to search for."),
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=500, help="Max messages."),
    date: Optional[str] = typer.Option(None, "--date", help="Only this date, YYYY-MM-DD."),
) -> None:
    """Search message text."""
    _show_messages(ctx, query=query, date_filter=None, date=date, limit=limit)


@app.command("semantic")
def semantic_command(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Natural-language-ish message search query."),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="Max indexed matches."),
    index_path: Optional[str] = typer.Option(
        None,
        "--index-path",
        help="Path to the local search index.",
    ),
) -> None:
    """Search the local all-message index."""
    try:
        rows = search_index(query, index_path=index_path, limit=limit)
    except FileNotFoundError:
        console.print("[yellow]No search index found yet.[/yellow]")
        console.print("Run `imsg index build` first.")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]Search index error:[/red] {exc}")
        raise typer.Exit(1)

    table = Table(title=f"Indexed matches ({len(rows)})", expand=True)
    table.add_column("When", no_wrap=True)
    table.add_column("Chat", overflow="fold")
    table.add_column("Sender", no_wrap=True)
    table.add_column("Text", overflow="fold")

    for row in rows:
        table.add_row(
            _format_date(row["date"], "%Y-%m-%d %H:%M"),
            row["chat_name"] or row["chat_identifier"] or "",
            row["sender"] or "Unknown",
            (row["text"] or "").replace("\n", " "),
        )

    console.print(table)


@index_app.command("build")
def index_build_command(
    ctx: typer.Context,
    index_path: Optional[str] = typer.Option(
        None,
        "--index-path",
        help="Path to write the local search index.",
    ),
) -> None:
    """Build or rebuild the all-message search index."""
    settings = _settings(ctx)
    conn = _connect(ctx)
    try:
        result = build_search_index(
            conn,
            index_path=index_path,
            db_path=settings.db_path,
        )
    finally:
        conn.close()

    console.print(
        "[green]Indexed[/green] "
        f"{result['message_count']} messages into {result['index_path']}."
    )
    console.print(
        f"[bold]Latest message:[/bold] {format_index_date(result['latest_message_date'])}"
    )


@index_app.command("status")
def index_status_command(
    index_path: Optional[str] = typer.Option(
        None,
        "--index-path",
        help="Path to the local search index.",
    ),
) -> None:
    """Show local search index status."""
    status = index_status(index_path=index_path)
    table = Table(title="Search index", expand=True)
    table.add_column("Field", style="bold")
    table.add_column("Value", overflow="fold")

    for key in [
        "exists",
        "index_path",
        "source_db_path",
        "built_at",
        "message_count",
        "latest_message_date",
        "version",
    ]:
        value = status.get(key)
        if key == "latest_message_date" and value and value.isdigit():
            value = format_index_date(int(value))
        table.add_row(key, value or "")

    console.print(table)


@app.command("today")
def today_command(
    ctx: typer.Context,
    query: Optional[str] = typer.Argument(None, help="Optional text to search for today."),
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=500, help="Max messages."),
) -> None:
    """Show today's messages, optionally filtered by text."""
    _show_messages(ctx, query=query, date_filter="today", date=None, limit=limit)


@app.command("export")
def export_command(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Contact name, partial phone/email, chat ID, or chat identifier."),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file or directory. Defaults to the current directory.",
    ),
    output_format: str = typer.Option(
        "yaml",
        "--format",
        "-f",
        case_sensitive=False,
        help="Export format: yaml or json.",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-n",
        min=1,
        max=100000,
        help="Most recent messages per chat.",
    ),
    include_groups: bool = typer.Option(
        False,
        "--include-groups",
        help="Include group chats when exporting by contact.",
    ),
) -> None:
    """Export chats for a person, phone, email, or chat."""
    output_format = output_format.lower()
    if output_format not in {"yaml", "json"}:
        console.print("[red]Format must be yaml or json.[/red]")
        raise typer.Exit(1)

    settings = _settings(ctx)
    conn = _connect(ctx)
    try:
        chats, contacts, handles, label = _resolve_export_target(
            conn,
            target,
            settings.contacts_db_paths,
            include_groups,
        )
        if not chats:
            console.print(f"[yellow]No Messages chats found for {target!r}.[/yellow]")
            raise typer.Exit(1)

        data = build_export(
            conn,
            chats,
            label=label,
            handles=handles,
            limit=limit,
            newest_first=True,
        )
        if contacts:
            data["contacts"] = contacts

        output_path = resolve_output_path(output, label, output_format)
        _ensure_parent_dir(output_path)
        write_export(data, output_format, output_path)
    finally:
        conn.close()

    console.print(
        "[green]Exported[/green] "
        f"{data['message_count']} messages from {data['conversation_count']} chat(s)."
    )
    console.print(f"[bold]File:[/bold] {output_path}")


def main() -> None:
    app()


def _print_banner() -> None:
    for line_index, line in enumerate(BANNER):
        text = Text()
        for column_index, char in enumerate(line):
            style = GRADIENT[(line_index + column_index) % len(GRADIENT)]
            text.append(char, style=style)
        console.print(text)


def _settings(ctx: typer.Context) -> Settings:
    return ctx.obj if isinstance(ctx.obj, Settings) else Settings(CHAT_DB_PATH, None)


def _connect(ctx: typer.Context):
    settings = _settings(ctx)
    try:
        return get_db_connection(settings.db_path)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        console.print("Grant Full Disk Access to the terminal or IDE running this command.")
        raise typer.Exit(1)


def _show_messages(
    ctx: typer.Context,
    query: Optional[str],
    date_filter: Optional[str],
    date: Optional[str],
    limit: int,
) -> None:
    conn = _connect(ctx)
    try:
        rows = search_message_rows(
            conn,
            search_term=query,
            date_filter=date_filter,
            specific_date=date,
            limit=limit,
            newest_first=True,
        )
    except ValueError:
        console.print("[red]Invalid date format.[/red] Use YYYY-MM-DD.")
        raise typer.Exit(1)
    finally:
        conn.close()

    table = Table(title=f"Messages ({len(rows)})", expand=True)
    table.add_column("When", no_wrap=True)
    table.add_column("Chat", overflow="fold")
    table.add_column("Sender", no_wrap=True)
    table.add_column("Text", overflow="fold")

    for row in rows:
        sender = "Me" if row["is_from_me"] else (row["handle_id"] or "Unknown")
        table.add_row(
            _format_date(row["date"], "%Y-%m-%d %H:%M"),
            row["chat_identifier"] or "",
            sender,
            (row["text"] or "").replace("\n", " "),
        )

    console.print(table)


def _resolve_export_target(
    conn,
    target: str,
    contacts_db_paths: Optional[List[str]],
    include_groups: bool,
) -> Tuple[List[object], List[dict], List[str], str]:
    exact_chat = find_chat_by_reference(conn, target)
    if exact_chat is not None:
        label = exact_chat["display_name"] or exact_chat["chat_identifier"] or target
        return [exact_chat], [], [], label

    contacts = find_contacts_by_name(target, contacts_db_paths)
    handles = sorted(
        {
            handle
            for contact in contacts
            for handle in contact["handles"]
        }
    )
    if handles:
        chats = find_chats_for_handles(conn, handles, include_groups=include_groups)
        if chats:
            label = contacts[0]["name"] if contacts else target
            return _unique_chats(chats), contacts, handles, str(label)

    chats = find_chats_by_query(conn, target, limit=20)
    return _unique_chats(chats), contacts, handles, target


def _unique_chats(chats: List[object]) -> List[object]:
    seen = set()
    unique = []
    for chat in chats:
        rowid = chat["ROWID"]
        if rowid in seen:
            continue
        seen.add(rowid)
        unique.append(chat)
    return unique


def _format_date(value, date_format: str) -> str:
    date_val = cocoa_to_datetime(value)
    if not date_val:
        return "N/A"
    return date_val.strftime(date_format)


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


if __name__ == "__main__":
    main()
