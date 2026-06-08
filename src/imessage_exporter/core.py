import sqlite3
import datetime
import csv
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional
from xml.sax.saxutils import escape
import yaml
from .contacts import handle_variants, normalize_phone
from .utils import cocoa_to_datetime, COCOA_EPOCH


@dataclass(frozen=True)
class MessageQuery:
    search_term: Optional[str] = None
    specific_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: Optional[int] = None
    offset: int = 0
    newest_first: bool = True

def list_chats(conn: sqlite3.Connection, limit: int = 50):
    """List recent chat sessions."""
    try:
        rows = list_recent_chats(conn, limit)
        print(f"{'ID':<5} | {'Identifier':<30} | {'Last Activity':<20}")
        print("-" * 60)
        for row in rows:
            date_val = cocoa_to_datetime(row['last_msg_date'])
            date_str = date_val.strftime('%Y-%m-%d %H:%M') if date_val else "N/A"
            ident = row['chat_identifier'] or "Unknown"
            display = row['display_name'] or ident
            print(f"{row['ROWID']:<5} | {display[:30]:<30} | {date_str:<20}")
    except sqlite3.Error as e:
        print(f"Database error: {e}")


def list_recent_chats(conn: sqlite3.Connection, limit: int = 50) -> List[sqlite3.Row]:
    """Return recent chat sessions ordered by latest activity first."""
    query = """
    SELECT 
        chat.ROWID, 
        chat.chat_identifier, 
        chat.display_name,
        chat.service_name,
        COUNT(message.ROWID) as message_count,
        MAX(message.date) as last_msg_date
    FROM chat
    LEFT JOIN chat_message_join ON chat.ROWID = chat_message_join.chat_id
    LEFT JOIN message ON chat_message_join.message_id = message.ROWID
    GROUP BY chat.ROWID
    ORDER BY last_msg_date DESC
    LIMIT ?
    """
    cursor = conn.cursor()
    cursor.execute(query, (limit,))
    return cursor.fetchall()

def search_messages(
    conn: sqlite3.Connection,
    search_term: Optional[str] = None,
    specific_date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Search and print messages based on filters."""
    try:
        rows = search_message_rows(conn, search_term, specific_date, start_date, end_date)
    except ValueError:
        print("Invalid date format. Please use YYYY-MM-DD")
        return
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return

    print(f"Found {len(rows)} messages.")
    print("-" * 80)

    for row in rows:
        date_val = cocoa_to_datetime(row['date'])
        date_str = date_val.strftime('%Y-%m-%d %H:%M:%S') if date_val else "Unknown Date"
        sender = "Me" if row['is_from_me'] else (row['handle_id'] or "Unknown")
        text = row['text']

        print(f"[{date_str}] {sender}: {text}")
        print("-" * 40)


def search_message_rows(
    conn: sqlite3.Connection,
    search_term: Optional[str] = None,
    specific_date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
    newest_first: bool = True,
    offset: int = 0,
) -> List[sqlite3.Row]:
    """Return matching messages."""
    spec = MessageQuery(
        search_term=search_term,
        specific_date=specific_date,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
        newest_first=newest_first,
    )
    return _fetch_message_rows(conn, spec)


def _fetch_message_rows(
    conn: sqlite3.Connection,
    spec: MessageQuery,
    chat_id: Optional[int] = None,
    chat_ids: Optional[List[int]] = None,
) -> List[sqlite3.Row]:
    clauses: List[str] = []
    params: List[object] = []
    if chat_ids is not None:
        _add_chat_ids_filter(clauses, params, chat_ids)
    else:
        _add_chat_filter(clauses, params, chat_id)
    _add_search_term(clauses, params, spec.search_term)
    _add_exact_date(clauses, params, spec.specific_date)
    _add_start_date(clauses, params, spec.start_date)
    _add_end_date(clauses, params, spec.end_date)
    has_offset = spec.offset > 0
    has_limit = bool(spec.limit) or has_offset
    query = _build_message_query(clauses, spec.newest_first, has_limit, has_offset)
    if has_limit:
        params.append(spec.limit if spec.limit else -1)
    if has_offset:
        params.append(spec.offset)
    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.fetchall()


def _build_message_query(
    clauses: List[str],
    newest_first: bool,
    has_limit: bool,
    has_offset: bool,
) -> str:
    query = """
    SELECT 
        message.ROWID,
        message.text,
        message.date,
        message.is_from_me,
        handle.id as handle_id,
        handle.service AS handle_service,
        chat.chat_identifier
    FROM message
    LEFT JOIN handle ON message.handle_id = handle.ROWID
    LEFT JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
    LEFT JOIN chat ON chat_message_join.chat_id = chat.ROWID
    WHERE message.text IS NOT NULL
    """
    query += "".join(clauses)
    direction = "DESC" if newest_first else "ASC"
    query += f" ORDER BY message.date {direction}"
    if has_limit:
        query += " LIMIT ?"
    if has_offset:
        query += " OFFSET ?"
    return query


def _add_chat_filter(
    clauses: List[str],
    params: List[object],
    chat_id: Optional[int],
) -> None:
    if chat_id is not None:
        clauses.append(" AND chat_message_join.chat_id = ?")
        params.append(chat_id)


def _add_chat_ids_filter(
    clauses: List[str],
    params: List[object],
    chat_ids: List[int],
) -> None:
    if chat_ids:
        placeholders = ", ".join("?" * len(chat_ids))
        clauses.append(f" AND chat_message_join.chat_id IN ({placeholders})")
        params.extend(chat_ids)


def _add_search_term(
    clauses: List[str],
    params: List[object],
    search_term: Optional[str],
) -> None:
    if search_term:
        clauses.append(" AND message.text LIKE ?")
        params.append(f"%{search_term}%")


def _add_exact_date(
    clauses: List[str],
    params: List[object],
    specific_date: Optional[str],
) -> None:
    if not specific_date:
        return
    start_cocoa = _date_to_cocoa(specific_date)
    end_cocoa = _date_to_cocoa(specific_date, days=1)
    clauses.append(" AND message.date >= ? AND message.date < ?")
    params.extend([start_cocoa, end_cocoa])


def _add_start_date(
    clauses: List[str],
    params: List[object],
    start_date: Optional[str],
) -> None:
    if start_date:
        clauses.append(" AND message.date >= ?")
        params.append(_date_to_cocoa(start_date))


def _add_end_date(
    clauses: List[str],
    params: List[object],
    end_date: Optional[str],
) -> None:
    if end_date:
        clauses.append(" AND message.date < ?")
        params.append(_date_to_cocoa(end_date, days=1))


def _date_to_cocoa(date_text: str, days: int = 0) -> float:
    try:
        target_date = datetime.datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Invalid date format. Please use YYYY-MM-DD")
    target_date += datetime.timedelta(days=days)
    return (target_date - COCOA_EPOCH).total_seconds() * 1_000_000_000


def find_chats_for_handles(
    conn: sqlite3.Connection,
    handles: Iterable[str],
    include_groups: bool = False,
) -> List[sqlite3.Row]:
    """Find chats that match the given phone/email handles."""
    variants = handle_variants(handles)
    if not variants:
        return []

    cursor = conn.cursor()
    params = list(variants)
    placeholders = ", ".join("?" for _ in params)

    if include_groups:
        query = f"""
        SELECT DISTINCT chat.*
        FROM chat
        LEFT JOIN chat_message_join ON chat.ROWID = chat_message_join.chat_id
        LEFT JOIN message ON chat_message_join.message_id = message.ROWID
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE chat.chat_identifier IN ({placeholders})
           OR handle.id IN ({placeholders})
        ORDER BY chat.ROWID ASC
        """
        params.extend(variants)
    else:
        query = f"""
        SELECT DISTINCT chat.*
        FROM chat
        WHERE chat.chat_identifier IN ({placeholders})
        ORDER BY chat.ROWID ASC
        """

    cursor.execute(query, params)
    return cursor.fetchall()


def find_chat_by_reference(conn: sqlite3.Connection, chat_ref: str) -> Optional[sqlite3.Row]:
    """Find a chat by ROWID or chat identifier."""
    cursor = conn.cursor()
    if chat_ref.isdigit():
        cursor.execute("SELECT * FROM chat WHERE ROWID = ?", (int(chat_ref),))
    else:
        cursor.execute("SELECT * FROM chat WHERE chat_identifier = ?", (chat_ref,))
    return cursor.fetchone()


def find_chats_by_query(
    conn: sqlite3.Connection,
    query_text: str,
    limit: int = 20,
) -> List[sqlite3.Row]:
    """Find chats by partial display name, chat identifier, phone, or handle."""
    query_text = (query_text or "").strip()
    if not query_text:
        return []

    terms = [f"%{query_text.casefold()}%"]
    digits = normalize_phone(query_text)
    if digits:
        terms.append(f"%{digits}%")

    clauses = []
    params = []
    for term in terms:
        clauses.extend(
            [
                "LOWER(COALESCE(chat.chat_identifier, '')) LIKE ?",
                "LOWER(COALESCE(chat.display_name, '')) LIKE ?",
                "LOWER(COALESCE(handle.id, '')) LIKE ?",
            ]
        )
        params.extend([term, term, term])

    sql = f"""
    SELECT
        chat.ROWID,
        chat.chat_identifier,
        chat.display_name,
        chat.service_name,
        COUNT(DISTINCT message.ROWID) as message_count,
        MAX(message.date) as last_msg_date
    FROM chat
    LEFT JOIN chat_message_join ON chat.ROWID = chat_message_join.chat_id
    LEFT JOIN message ON chat_message_join.message_id = message.ROWID
    LEFT JOIN handle ON message.handle_id = handle.ROWID
    WHERE {" OR ".join(clauses)}
    GROUP BY chat.ROWID
    ORDER BY last_msg_date DESC
    LIMIT ?
    """
    params.append(limit)

    cursor = conn.cursor()
    cursor.execute(sql, params)
    return cursor.fetchall()


def build_export(
    conn: sqlite3.Connection,
    chats: Iterable[sqlite3.Row],
    label: Optional[str] = None,
    handles: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
    newest_first: bool = False,
    filters: Optional[MessageQuery] = None,
    merged: bool = False,
) -> Dict[str, object]:
    """Build a serializable conversation export for the given chats."""
    chat_list = list(chats)
    message_query = filters or MessageQuery(limit=limit, newest_first=newest_first)
    if merged:
        conversations = _build_merged_conversations(conn, chat_list, label, message_query)
    else:
        conversations = [
            {"chat": _chat_payload(chat), "messages": _messages_for_chat(conn, chat["ROWID"], message_query)}
            for chat in chat_list
        ]

    return {
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "handles": list(handles or []),
        "conversation_count": len(chat_list),
        "message_count": sum(len(item["messages"]) for item in conversations),
        "conversations": conversations,
    }


def _build_merged_conversations(
    conn: sqlite3.Connection,
    chat_list: List[sqlite3.Row],
    label: Optional[str],
    spec: MessageQuery,
) -> List[Dict[str, object]]:
    chat_ids = [chat["ROWID"] for chat in chat_list]
    rows = _fetch_message_rows(conn, spec, chat_ids=chat_ids)
    messages = [_message_payload(row) for row in rows]
    return [
        {
            "chat": {"rowid": None, "identifier": label, "display_name": None, "service": None},
            "messages": messages,
        }
    ]


def render_export(data: Dict[str, object], output_format: str = "yaml") -> str:
    """Render an export payload as YAML, JSON, or CSV."""
    if output_format == "json":
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if output_format == "csv":
        return _render_export_csv(data)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def write_export(data: Dict[str, object], output_format: str, output_path: Optional[str]) -> None:
    if output_format == "xlsx":
        if not output_path:
            raise ValueError("XLSX exports require an output path.")
        _write_export_xlsx(data, output_path)
        print(f"Wrote {data['message_count']} messages to {output_path}")
        return

    rendered = render_export(data, output_format)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write(rendered)
        print(f"Wrote {data['message_count']} messages to {output_path}")
    else:
        print(rendered, end="")


def _chat_payload(chat: sqlite3.Row) -> Dict[str, object]:
    return {
        "rowid": chat["ROWID"],
        "identifier": chat["chat_identifier"],
        "display_name": chat["display_name"],
        "service": chat["service_name"],
    }


def default_export_path(
    label: Optional[str],
    output_format: str,
    directory: Optional[str] = None,
) -> str:
    """Build a default export path in the current working directory."""
    directory = directory or os.getcwd()
    name = _slugify(label or "messages")
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(directory, f"imessage-{name}-{timestamp}.{output_format}")


def resolve_output_path(
    output_path: Optional[str],
    label: Optional[str],
    output_format: str,
) -> str:
    """Resolve a CLI output option into a concrete file path."""
    if not output_path:
        return default_export_path(label, output_format)

    expanded = os.path.expanduser(output_path)
    if os.path.isdir(expanded):
        return default_export_path(label, output_format, expanded)

    return expanded


def _messages_for_chat(
    conn: sqlite3.Connection,
    chat_id: int,
    spec: MessageQuery,
) -> List[Dict[str, object]]:
    rows = _fetch_message_rows(conn, spec, chat_id)
    return [_message_payload(row) for row in rows]


def _message_payload(row: sqlite3.Row) -> Dict[str, object]:
    date_val = cocoa_to_datetime(row["date"])
    sender = "Me" if row["is_from_me"] else (row["handle_id"] or "Unknown")
    return {
        "id": row["ROWID"],
        "date": date_val.isoformat(sep=" ", timespec="seconds") if date_val else None,
        "sender": sender,
        "from_me": bool(row["is_from_me"]),
        "handle": row["handle_id"],
        "service": row["handle_service"],
        "text": row["text"],
    }


def _flatten_export_messages(data: Dict[str, object]) -> List[Dict[str, object]]:
    rows = []
    for conversation in data.get("conversations", []):
        chat = conversation.get("chat", {})
        for message in conversation.get("messages", []):
            rows.append(
                {
                    "conversation_rowid": chat.get("rowid"),
                    "conversation_name": chat.get("display_name"),
                    "chat_identifier": chat.get("identifier"),
                    "chat_service": chat.get("service"),
                    "message_id": message.get("id"),
                    "date": message.get("date"),
                    "sender": message.get("sender"),
                    "from_me": message.get("from_me"),
                    "handle": message.get("handle"),
                    "handle_service": message.get("service"),
                    "text": message.get("text"),
                }
            )
    return rows


def _render_export_csv(data: Dict[str, object]) -> str:
    output = io.StringIO()
    rows = _flatten_export_messages(data)
    fieldnames = [
        "conversation_rowid",
        "conversation_name",
        "chat_identifier",
        "chat_service",
        "message_id",
        "date",
        "sender",
        "from_me",
        "handle",
        "handle_service",
        "text",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _write_export_xlsx(data: Dict[str, object], output_path: str) -> None:
    rows = _flatten_export_messages(data)
    conversations = [
        conversation.get("chat", {})
        for conversation in data.get("conversations", [])
    ]
    daily_counts = _daily_message_counts(rows)

    sheets = [
        (
            "Messages",
            [
                "conversation_rowid",
                "conversation_name",
                "chat_identifier",
                "chat_service",
                "message_id",
                "date",
                "sender",
                "from_me",
                "handle",
                "handle_service",
                "text",
            ],
            rows,
        ),
        (
            "Conversations",
            ["rowid", "display_name", "identifier", "service"],
            conversations,
        ),
        (
            "Daily Counts",
            ["date", "messages"],
            daily_counts,
        ),
    ]

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", _xlsx_content_types(len(sheets)))
        workbook.writestr("_rels/.rels", _xlsx_root_rels())
        workbook.writestr("xl/workbook.xml", _xlsx_workbook(sheets))
        workbook.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels(len(sheets)))
        workbook.writestr("xl/styles.xml", _xlsx_styles())
        for index, (name, headers, sheet_rows) in enumerate(sheets, start=1):
            workbook.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _xlsx_sheet(headers, sheet_rows),
            )


def _daily_message_counts(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    counts: Dict[str, int] = {}
    for row in rows:
        date = str(row.get("date") or "")[:10]
        if not date:
            continue
        counts[date] = counts.get(date, 0) + 1
    return [
        {"date": date, "messages": count}
        for date, count in sorted(counts.items())
    ]


def _xlsx_sheet(headers: List[str], rows: List[Dict[str, object]]) -> str:
    sheet_rows = [_xlsx_row(1, headers)]
    for row_index, row in enumerate(rows, start=2):
        sheet_rows.append(
            _xlsx_row(
                row_index,
                [row.get(header, "") for header in headers],
            )
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(sheet_rows)
        + "</sheetData></worksheet>"
    )


def _xlsx_row(row_index: int, values: List[object]) -> str:
    cells = []
    for column_index, value in enumerate(values, start=1):
        cell_ref = f"{_xlsx_column_name(column_index)}{row_index}"
        cells.append(_xlsx_cell(cell_ref, value))
    return f'<row r="{row_index}">{"".join(cells)}</row>'


def _xlsx_cell(cell_ref: str, value: object) -> str:
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{cell_ref}"><v>{value}</v></c>'
    text = escape("" if value is None else str(value))
    preserve = ' xml:space="preserve"' if text.strip() != text else ""
    return f'<c r="{cell_ref}" t="inlineStr"><is><t{preserve}>{text}</t></is></c>'


def _xlsx_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_content_types(sheet_count: int) -> str:
    sheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f"{sheet_overrides}</Types>"
    )


def _xlsx_root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )


def _xlsx_workbook(sheets) -> str:
    sheet_nodes = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _, _) in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_nodes}</sheets></workbook>"
    )


def _xlsx_workbook_rels(sheet_count: int) -> str:
    sheet_rels = "".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    styles_id = sheet_count + 1
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{sheet_rels}"
        f'<Relationship Id="rId{styles_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>'
    )


def _xlsx_styles() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '</styleSheet>'
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "messages"
