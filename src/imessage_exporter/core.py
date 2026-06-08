import sqlite3
import datetime
import json
import os
import re
from typing import Dict, Iterable, List, Optional
import yaml
from .contacts import handle_variants, normalize_phone
from .utils import cocoa_to_datetime, COCOA_EPOCH

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

def search_messages(conn: sqlite3.Connection, search_term: Optional[str] = None, date_filter: Optional[str] = None, specific_date: Optional[str] = None):
    """Search and print messages based on filters."""
    try:
        rows = search_message_rows(conn, search_term, date_filter, specific_date)
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
    date_filter: Optional[str] = None,
    specific_date: Optional[str] = None,
    limit: int = 50,
    newest_first: bool = True,
) -> List[sqlite3.Row]:
    """Return matching messages."""
    query = """
    SELECT 
        message.ROWID,
        message.text,
        message.date,
        message.is_from_me,
        handle.id as handle_id,
        chat.chat_identifier
    FROM message
    LEFT JOIN handle ON message.handle_id = handle.ROWID
    LEFT JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
    LEFT JOIN chat ON chat_message_join.chat_id = chat.ROWID
    WHERE message.text IS NOT NULL
    """
    params = []

    if search_term:
        query += " AND message.text LIKE ?"
        params.append(f"%{search_term}%")

    if date_filter == "today":
        now = datetime.datetime.now()
        start_of_day = datetime.datetime(now.year, now.month, now.day)
        delta = start_of_day - COCOA_EPOCH
        cocoa_start = delta.total_seconds() * 1_000_000_000
        query += " AND message.date >= ?"
        params.append(cocoa_start)
    
    if specific_date:
        try:
            target_date = datetime.datetime.strptime(specific_date, "%Y-%m-%d")
            start_delta = target_date - COCOA_EPOCH
            end_delta = target_date + datetime.timedelta(days=1) - COCOA_EPOCH
            
            start_cocoa = start_delta.total_seconds() * 1_000_000_000
            end_cocoa = end_delta.total_seconds() * 1_000_000_000
            
            query += " AND message.date >= ? AND message.date < ?"
            params.append(start_cocoa)
            params.append(end_cocoa)
        except ValueError:
            raise ValueError("Invalid date format. Please use YYYY-MM-DD")

    direction = "DESC" if newest_first else "ASC"
    query += f" ORDER BY message.date {direction}"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.fetchall()


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
) -> Dict[str, object]:
    """Build a serializable conversation export for the given chats."""
    conversations = []
    for chat in chats:
        conversations.append(
            {
                "chat": _chat_payload(chat),
                "messages": _messages_for_chat(conn, chat["ROWID"], limit, newest_first),
            }
        )

    return {
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "handles": list(handles or []),
        "conversation_count": len(conversations),
        "message_count": sum(len(item["messages"]) for item in conversations),
        "conversations": conversations,
    }


def render_export(data: Dict[str, object], output_format: str = "yaml") -> str:
    """Render an export payload as YAML or JSON."""
    if output_format == "json":
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def write_export(data: Dict[str, object], output_format: str, output_path: Optional[str]) -> None:
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
    limit: Optional[int] = None,
    newest_first: bool = False,
) -> List[Dict[str, object]]:
    cursor = conn.cursor()
    direction = "DESC" if newest_first else "ASC"
    query = f"""
        SELECT
            message.ROWID,
            message.text,
            message.date,
            message.is_from_me,
            handle.id AS handle_id,
            handle.service AS handle_service
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        INNER JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
        WHERE chat_message_join.chat_id = ?
          AND message.text IS NOT NULL
        ORDER BY message.date {direction}
        """
    params = [chat_id]
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    cursor.execute(query, params)
    return [_message_payload(row) for row in cursor.fetchall()]


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


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "messages"
