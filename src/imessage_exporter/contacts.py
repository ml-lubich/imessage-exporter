import glob
import os
import re
import sqlite3
from typing import Dict, Iterable, List, Optional


ADDRESS_BOOK_ROOT = os.path.expanduser("~/Library/Application Support/AddressBook")


def default_contacts_db_paths() -> List[str]:
    """Return likely macOS Contacts database paths."""
    patterns = [
        os.path.join(ADDRESS_BOOK_ROOT, "AddressBook-v*.abcddb"),
        os.path.join(ADDRESS_BOOK_ROOT, "Sources", "*", "AddressBook-v*.abcddb"),
    ]
    paths = []
    for pattern in patterns:
        paths.extend(glob.glob(pattern))
    return sorted(dict.fromkeys(paths))


def normalize_phone(value: str) -> str:
    """Normalize a phone-ish value for matching Messages handles."""
    return re.sub(r"\D", "", value or "")


def handle_variants(handles: Iterable[str]) -> List[str]:
    """Build handle variants that commonly appear in chat identifiers."""
    variants = set()
    for handle in handles:
        if not handle:
            continue
        value = handle.strip()
        variants.add(value)
        variants.add(value.lower())

        digits = normalize_phone(value)
        if digits:
            variants.add(digits)
            variants.add("+" + digits)
            if len(digits) == 11 and digits.startswith("1"):
                variants.add(digits[1:])

    return sorted(variants)


def find_contacts_by_name(
    name: str,
    db_paths: Optional[Iterable[str]] = None,
) -> List[Dict[str, object]]:
    """Find Contacts records whose visible name contains all query tokens."""
    query_tokens = [token.casefold() for token in name.split() if token.strip()]
    if not query_tokens:
        return []

    contacts = []
    for db_path in db_paths or default_contacts_db_paths():
        if not os.path.exists(db_path):
            continue

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    Z_PK,
                    COALESCE(ZFIRSTNAME, '') AS first_name,
                    COALESCE(ZMIDDLENAME, '') AS middle_name,
                    COALESCE(ZLASTNAME, '') AS last_name,
                    COALESCE(ZNICKNAME, '') AS nickname,
                    COALESCE(ZORGANIZATION, '') AS organization,
                    COALESCE(ZNAME, '') AS name
                FROM ZABCDRECORD
                """
            )

            for row in cursor.fetchall():
                visible_name = " ".join(
                    value
                    for value in [
                        row["first_name"],
                        row["middle_name"],
                        row["last_name"],
                        row["nickname"],
                        row["organization"],
                        row["name"],
                    ]
                    if value
                )
                searchable = visible_name.casefold()
                if not all(token in searchable for token in query_tokens):
                    continue

                handles = _contact_handles(conn, row["Z_PK"])
                contacts.append(
                    {
                        "id": row["Z_PK"],
                        "name": " ".join(
                            value
                            for value in [
                                row["first_name"],
                                row["middle_name"],
                                row["last_name"],
                            ]
                            if value
                        )
                        or visible_name,
                        "handles": handles,
                        "contacts_db": db_path,
                    }
                )
        finally:
            conn.close()

    return contacts


def _contact_handles(conn: sqlite3.Connection, contact_id: int) -> List[str]:
    handles = []
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT ZFULLNUMBER AS value
        FROM ZABCDPHONENUMBER
        WHERE ZOWNER = ? OR Z22_OWNER = ?
        """,
        (contact_id, contact_id),
    )
    handles.extend(row["value"] for row in cursor.fetchall() if row["value"])

    cursor.execute(
        """
        SELECT ZADDRESS AS value
        FROM ZABCDEMAILADDRESS
        WHERE ZOWNER = ? OR Z22_OWNER = ?
        """,
        (contact_id, contact_id),
    )
    handles.extend(row["value"] for row in cursor.fetchall() if row["value"])

    return sorted(dict.fromkeys(handles))
