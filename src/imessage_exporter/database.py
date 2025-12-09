import sqlite3
import os
import sys
from typing import Optional

# Default path
CHAT_DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")

def get_db_connection(db_path: str = CHAT_DB_PATH) -> sqlite3.Connection:
    """
    Establish a read-only connection to the iMessage database.
    
    Args:
        db_path: Path to the chat.db file.
    
    Returns:
        sqlite3.Connection object.
        
    Raises:
        FileNotFoundError: If the database file does not exist.
        sqlite3.OperationalError: If permissions are insufficient.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")
    
    try:
        # Open in read-only mode with URI
        # We use uri=True to allow passing query parameters like mode=ro
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as e:
        # Re-raise or handle? The original script exited. 
        # Better to let the caller handle it, but for now we print and exit to match behavior,
        # or better yet, just re-raise so CLI can handle it cleanly.
        raise e
