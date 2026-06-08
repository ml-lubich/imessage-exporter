import os
from dataclasses import dataclass
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .contacts import find_contacts_by_name, handle_variants
from .core import (
    MessageQuery,
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
HELP_OPTIONS = ["-h", "--help"]
app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": HELP_OPTIONS},
    help="Export, search, and browse local iMessage chats.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)
index_app = typer.Typer(
    context_settings={"help_option_names": HELP_OPTIONS},
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

CONTACT_OPTION_LIMIT = 5
CHAT_OPTION_LIMIT = 10
DEFAULT_LIST_LIMIT = 25
DEFAULT_VIEW_PAGE_SIZE = 10
EXPORT_FORMATS = {"yaml", "json", "csv", "xlsx"}


@dataclass
class Settings:
    db_path: str
    contacts_db_paths: Optional[List[str]]


@dataclass
class TargetResolution:
    chats: List[object]
    contacts: List[dict]
    handles: List[str]
    label: str
    ambiguous: bool = False
    too_many: bool = False


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
    target: Optional[str] = typer.Argument(
        None,
        help="Number of chats to show, or a contact/phone/email/chat search.",
    ),
    limit: int = typer.Option(
        DEFAULT_LIST_LIMIT,
        "--limit",
        "-n",
        min=1,
        max=500,
        help="Messages to show when listing one conversation.",
    ),
) -> None:
    """List recent chats, or recent messages for one matched chat."""
    if target and target.isdigit() and 1 <= int(target) <= 500 and limit == DEFAULT_LIST_LIMIT:
        _list_recent_chat_table(ctx, int(target))
        return

    if not target:
        _list_recent_chat_table(ctx, limit)
        return

    settings = _settings(ctx)
    conn = _connect(ctx)
    try:
        resolution = _resolve_target(
            conn,
            target,
            settings.contacts_db_paths,
            include_groups=False,
        )
        if _handle_unselected_target(target, resolution):
            raise typer.Exit(1)

        if len(resolution.chats) > 1:
            _print_chats_table(
                resolution.chats,
                title=f"Conversations matching {target!r}",
            )
            console.print(
                "[yellow]More than one conversation matched.[/yellow] "
                "Run `imsg list <ID>` or search more closely."
            )
            raise typer.Exit(1)

        data = build_export(
            conn,
            resolution.chats,
            label=resolution.label,
            handles=resolution.handles,
            limit=limit,
            newest_first=True,
            merged=True,
        )
    finally:
        conn.close()

    _print_export_messages(
        data,
        title=f"Recent messages for {resolution.label} ({data['message_count']})",
    )



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
    query: Optional[str] = typer.Argument(None, help="Optional text to search for."),
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=500, help="Max messages."),
    date: Optional[str] = typer.Option(None, "--date", help="Only this date, YYYY-MM-DD."),
    start_date: Optional[str] = typer.Option(
        None,
        "--from",
        help="Start date, YYYY-MM-DD, inclusive.",
    ),
    end_date: Optional[str] = typer.Option(
        None,
        "--to",
        help="End date, YYYY-MM-DD, inclusive.",
    ),
) -> None:
    """Search messages by text, date, range, or text plus range."""
    _show_messages(ctx, query, date, start_date, end_date, limit)


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


@app.command("view")
def view_command(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Contact name, phone/email, chat ID, or chat identifier."),
    page: int = typer.Option(1, "--page", "-p", min=1, help="Page number to show."),
    page_size: int = typer.Option(DEFAULT_VIEW_PAGE_SIZE, "--page-size", "-n", min=1, max=500, help="Messages per page."),
    all_messages: bool = typer.Option(False, "--all", "-a", help="Show all messages (ignores --page and --page-size)."),
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Only messages containing this text."),
    date: Optional[str] = typer.Option(None, "--date", help="Only this date, YYYY-MM-DD."),
    start_date: Optional[str] = typer.Option(None, "--from", help="Start date, YYYY-MM-DD, inclusive."),
    end_date: Optional[str] = typer.Option(None, "--to", help="End date, YYYY-MM-DD, inclusive."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Also export all matching messages to this file or directory."),
    output_format: str = typer.Option("yaml", "--format", "-f", case_sensitive=False, help="Export format for --output."),
    include_groups: bool = typer.Option(False, "--include-groups", help="Include group chats when resolving contacts."),
) -> None:
    """Page through one conversation and optionally export filtered messages."""
    effective_limit = None if all_messages else page_size
    effective_page = 1 if all_messages else page
    query = _message_query(search, date, start_date, end_date, effective_limit, effective_page)
    data = _load_export_data(ctx, target, include_groups, query, merged=True)
    _print_export_messages(data, title=_view_title(data, effective_page, effective_limit))
    _print_view_hint(target, effective_page, effective_limit, data)
    if output:
        export_query = _message_query(search, date, start_date, end_date, None, 1)
        export_data = _load_export_data(ctx, target, include_groups, export_query)
        _write_export_data(export_data, output, output_format)


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
        help="Export format: yaml, json, csv, or xlsx.",
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
    search: Optional[str] = typer.Option(
        None,
        "--search",
        "-s",
        help="Only export messages containing this text.",
    ),
    date: Optional[str] = typer.Option(None, "--date", help="Only this date, YYYY-MM-DD."),
    start_date: Optional[str] = typer.Option(
        None,
        "--from",
        help="Start date, YYYY-MM-DD, inclusive.",
    ),
    end_date: Optional[str] = typer.Option(
        None,
        "--to",
        help="End date, YYYY-MM-DD, inclusive.",
    ),
) -> None:
    """Export chats for a person, phone, email, or chat."""
    query = _message_query(search, date, start_date, end_date, limit, 1)
    data = _load_export_data(ctx, target, include_groups, query)
    output_path = _write_export_data(data, output, output_format)
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


def _message_query(
    search: Optional[str],
    date: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    limit: Optional[int],
    page: int,
) -> MessageQuery:
    if date and (start_date or end_date):
        console.print("[red]Use either --date or --from/--to, not both.[/red]")
        raise typer.Exit(1)
    offset = (page - 1) * limit if limit else 0
    return MessageQuery(search, date, start_date, end_date, limit, offset, True)


def _load_export_data(
    ctx: typer.Context,
    target: str,
    include_groups: bool,
    query: MessageQuery,
    merged: bool = False,
) -> dict:
    settings = _settings(ctx)
    conn = _connect(ctx)
    try:
        resolution = _resolve_target(conn, target, settings.contacts_db_paths, include_groups)
        if _handle_unselected_target(target, resolution):
            raise typer.Exit(1)
        data = build_export(conn, resolution.chats, resolution.label, resolution.handles, filters=query, merged=merged)
        if resolution.contacts:
            data["contacts"] = resolution.contacts
        return data
    except ValueError:
        console.print("[red]Invalid date format.[/red] Use YYYY-MM-DD.")
        raise typer.Exit(1)
    finally:
        conn.close()


def _write_export_data(
    data: dict,
    output: Optional[str],
    output_format: str,
) -> str:
    output_format = _export_format(output_format)
    output_path = resolve_output_path(output, str(data.get("label") or "messages"), output_format)
    _ensure_parent_dir(output_path)
    write_export(data, output_format, output_path)
    return output_path


def _export_format(output_format: str) -> str:
    normalized = output_format.lower()
    if normalized not in EXPORT_FORMATS:
        console.print("[red]Format must be yaml, json, csv, or xlsx.[/red]")
        raise typer.Exit(1)
    return normalized


def _show_messages(
    ctx: typer.Context,
    query: Optional[str],
    date: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    limit: int,
) -> None:
    if date and (start_date or end_date):
        console.print("[red]Use either --date or --from/--to, not both.[/red]")
        raise typer.Exit(1)

    conn = _connect(ctx)
    try:
        rows = search_message_rows(
            conn,
            search_term=query,
            specific_date=date,
            start_date=start_date,
            end_date=end_date,
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


def _list_recent_chat_table(ctx: typer.Context, limit: int) -> None:
    conn = _connect(ctx)
    try:
        rows = list_recent_chats(conn, limit)
    finally:
        conn.close()

    _print_chats_table(rows, title=f"Recent chats ({len(rows)})")


def _resolve_target(
    conn,
    target: str,
    contacts_db_paths: Optional[List[str]],
    include_groups: bool,
) -> TargetResolution:
    exact_chat = find_chat_by_reference(conn, target)
    if exact_chat is not None:
        label = exact_chat["display_name"] or exact_chat["chat_identifier"] or target
        return TargetResolution([exact_chat], [], [], label)

    contacts = find_contacts_by_name(target, contacts_db_paths)
    if len(contacts) > CONTACT_OPTION_LIMIT:
        return TargetResolution([], contacts, [], target, too_many=True)

    direct_chats = _unique_chats(find_chats_by_query(conn, target, limit=CHAT_OPTION_LIMIT + 1))
    if len(direct_chats) > CHAT_OPTION_LIMIT:
        return TargetResolution(direct_chats, contacts, [], target, too_many=True)

    if len(contacts) > 1:
        return TargetResolution(direct_chats, contacts, [], target, ambiguous=True)

    handles = sorted(
        {
            handle
            for contact in contacts
            for handle in contact["handles"]
        }
    )
    if len(contacts) == 1 and handles:
        chats = _unique_chats(
            find_chats_for_handles(conn, handles, include_groups=include_groups)
        )
        if chats:
            label = contacts[0]["name"] if contacts else target
            return TargetResolution(chats, contacts, handles, str(label))

    if len(direct_chats) > 1:
        return TargetResolution(direct_chats, contacts, handles, target, ambiguous=True)

    label = target
    if len(direct_chats) == 1:
        chat = direct_chats[0]
        label = chat["display_name"] or chat["chat_identifier"] or target
    return TargetResolution(direct_chats, contacts, handles, str(label))


def _handle_unselected_target(target: str, resolution: TargetResolution) -> bool:
    if resolution.too_many:
        if resolution.contacts:
            _print_contacts_table(
                resolution.contacts[:CONTACT_OPTION_LIMIT],
                title=f"Contacts matching {target!r}",
            )
        if resolution.chats:
            _print_chats_table(
                resolution.chats[:CHAT_OPTION_LIMIT],
                title=f"Conversations matching {target!r}",
            )
        console.print(
            "[yellow]Too many matches.[/yellow] "
            "Please search more closely, or use an exact chat ID, phone, or email."
        )
        return True

    if resolution.ambiguous:
        if resolution.contacts:
            _print_contacts_table(
                resolution.contacts,
                title=f"Contacts matching {target!r}",
            )
        if resolution.chats:
            _print_chats_table(
                resolution.chats,
                title=f"Conversations matching {target!r}",
            )
        console.print(
            "[yellow]More than one match found.[/yellow] "
            "Please use a more specific name, phone, email, or chat ID."
        )
        return True

    if not resolution.chats:
        console.print(f"[yellow]No Messages chats found for {target!r}.[/yellow]")
        return True

    return False


def _print_chats_table(chats: List[object], title: str) -> None:
    table = Table(title=title, expand=True)
    table.add_column("ID", style="bold cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Identifier", overflow="fold")
    table.add_column("Messages", justify="right")
    table.add_column("Last activity", no_wrap=True)

    for row in chats:
        table.add_row(
            str(row["ROWID"]),
            row["display_name"] or row["chat_identifier"] or "Unknown",
            row["chat_identifier"] or "",
            str(row["message_count"] or 0) if "message_count" in row.keys() else "",
            _format_date(row["last_msg_date"], "%Y-%m-%d %H:%M")
            if "last_msg_date" in row.keys()
            else "",
        )

    console.print(table)


def _print_contacts_table(contacts: List[dict], title: str) -> None:
    table = Table(title=title, expand=True)
    table.add_column("Name", style="bold")
    table.add_column("Handles", overflow="fold")
    for contact in contacts:
        table.add_row(
            str(contact["name"]),
            ", ".join(contact["handles"]) or "No phone/email handles",
        )
    console.print(table)


def _print_export_messages(data: dict, title: str) -> None:
    table = Table(title=title, expand=True)
    table.add_column("When", no_wrap=True)
    table.add_column("Chat", overflow="fold")
    table.add_column("Sender", no_wrap=True)
    table.add_column("Text", overflow="fold")

    handle_to_name = _build_handle_name_map(data.get("contacts") or [])

    for conversation in data.get("conversations", []):
        chat = conversation.get("chat", {})
        identifier = chat.get("identifier") or ""
        chat_name = (
            chat.get("display_name")
            or handle_to_name.get(identifier)
            or identifier
        )
        for message in conversation.get("messages", []):
            table.add_row(
                str(message.get("date") or "N/A"),
                str(chat_name),
                str(message.get("sender") or "Unknown"),
                str(message.get("text") or "").replace("\n", " "),
            )

    console.print(table)


def _view_title(data: dict, page: int, page_size: Optional[int]) -> str:
    label = str(data.get("label") or "conversation")
    count = int(data.get("message_count") or 0)
    if page_size is None:
        return f"{label} (all {count})"
    return f"{label} page {page} ({count}/{page_size})"


def _print_view_hint(target: str, page: int, page_size: Optional[int], data: dict) -> None:
    if page_size is None:
        return
    count = int(data.get("message_count") or 0)
    if count == page_size:
        console.print(f"[dim]Next page:[/dim] imsg view {target!r} --page {page + 1}")
        return
    console.print("[dim]No more messages on the next page.[/dim]")


def _build_handle_name_map(contacts: list) -> dict:
    result: dict = {}
    for contact in contacts:
        name = contact.get("name") or ""
        if not name:
            continue
        for variant in handle_variants(contact.get("handles") or []):
            result[variant] = name
    return result


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
