import datetime
import os
import sqlite3
from typing import Dict, Iterable, List, Optional

from .utils import cocoa_to_datetime


INDEX_VERSION = 1
DEFAULT_INDEX_PATH = os.path.expanduser(
    "~/Library/Caches/imessage-exporter/search-index.sqlite"
)


def resolve_index_path(index_path: Optional[str] = None) -> str:
    return os.path.expanduser(index_path or DEFAULT_INDEX_PATH)


def build_search_index(
    source_conn: sqlite3.Connection,
    index_path: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, object]:
    """Build or rebuild the local message search index."""
    resolved = resolve_index_path(index_path)
    parent = os.path.dirname(os.path.abspath(resolved))
    if parent:
        os.makedirs(parent, exist_ok=True)

    index_conn = sqlite3.connect(resolved)
    try:
        _reset_schema(index_conn)
        messages = list(_indexable_messages(source_conn))
        with index_conn:
            for message in messages:
                index_conn.execute(
                    """
                    INSERT INTO messages (
                        message_id,
                        text,
                        date,
                        is_from_me,
                        sender,
                        chat_identifier,
                        chat_name
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message["message_id"],
                        message["text"],
                        message["date"],
                        message["is_from_me"],
                        message["sender"],
                        message["chat_identifier"],
                        message["chat_name"],
                    ),
                )

            index_conn.execute(
                """
                INSERT INTO metadata (key, value)
                VALUES
                    ('version', ?),
                    ('source_db_path', ?),
                    ('built_at', ?),
                    ('message_count', ?),
                    ('latest_message_date', ?)
                """,
                (
                    str(INDEX_VERSION),
                    os.path.expanduser(db_path or ""),
                    datetime.datetime.now().isoformat(timespec="seconds"),
                    str(len(messages)),
                    str(max((message["date"] or 0 for message in messages), default=0)),
                ),
            )
        return {
            "index_path": resolved,
            "message_count": len(messages),
            "latest_message_date": max(
                (message["date"] or 0 for message in messages),
                default=None,
            ),
        }
    finally:
        index_conn.close()


def search_index(
    query: str,
    index_path: Optional[str] = None,
    limit: int = 20,
) -> List[sqlite3.Row]:
    """Search the local message index."""
    resolved = resolve_index_path(index_path)
    if not os.path.exists(resolved):
        raise FileNotFoundError("Search index has not been built yet.")

    conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_index_exists(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                message_id,
                text,
                date,
                is_from_me,
                sender,
                chat_identifier,
                chat_name,
                bm25(messages) AS score
            FROM messages
            WHERE messages MATCH ?
            ORDER BY score ASC
            LIMIT ?
            """,
            (_fts_query(query), limit),
        )
        return cursor.fetchall()
    finally:
        conn.close()


def index_status(index_path: Optional[str] = None) -> Dict[str, Optional[str]]:
    resolved = resolve_index_path(index_path)
    if not os.path.exists(resolved):
        return {"index_path": resolved, "exists": "false"}

    conn = sqlite3.connect(resolved)
    try:
        metadata = dict(conn.execute("SELECT key, value FROM metadata").fetchall())
        metadata["index_path"] = resolved
        metadata["exists"] = "true"
        return metadata
    except sqlite3.Error:
        return {"index_path": resolved, "exists": "broken"}
    finally:
        conn.close()


def format_index_date(value: Optional[int]) -> str:
    date_value = cocoa_to_datetime(value)
    if not date_value:
        return "N/A"
    return date_value.strftime("%Y-%m-%d %H:%M")


def _reset_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("DROP TABLE IF EXISTS messages")
        conn.execute("DROP TABLE IF EXISTS metadata")
        conn.execute(
            """
            CREATE VIRTUAL TABLE messages USING fts5(
                message_id UNINDEXED,
                text,
                sender,
                chat_identifier,
                chat_name,
                date UNINDEXED,
                is_from_me UNINDEXED,
                tokenize='unicode61'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )


def _ensure_index_exists(conn: sqlite3.Connection) -> None:
    cursor = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'messages'
        """
    )
    if cursor.fetchone() is None:
        raise FileNotFoundError("Search index has not been built yet.")


def _indexable_messages(conn: sqlite3.Connection) -> Iterable[Dict[str, object]]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            message.ROWID AS message_id,
            message.text,
            message.date,
            message.is_from_me,
            handle.id AS handle_id,
            chat.chat_identifier,
            chat.display_name AS chat_name
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        LEFT JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
        LEFT JOIN chat ON chat_message_join.chat_id = chat.ROWID
        WHERE message.text IS NOT NULL
          AND TRIM(message.text) != ''
        ORDER BY message.date ASC
        """
    )
    for row in cursor.fetchall():
        yield {
            "message_id": row["message_id"],
            "text": row["text"],
            "date": row["date"],
            "is_from_me": row["is_from_me"],
            "sender": "Me" if row["is_from_me"] else (row["handle_id"] or "Unknown"),
            "chat_identifier": row["chat_identifier"] or "",
            "chat_name": row["chat_name"] or row["chat_identifier"] or "",
        }


def _fts_query(query: str) -> str:
    tokens = [token.replace('"', "") for token in query.split() if token.strip()]
    if not tokens:
        return '""'
    return " OR ".join(f'"{token}"' for token in tokens)
