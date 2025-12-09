import sqlite3
import os
import datetime

def create_dummy_db(db_path: str):
    """Create a dummy chat.db with sample data."""
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
    CREATE TABLE chat (
        ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_identifier TEXT,
        display_name TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE handle (
        ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE message (
        ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT,
        date INTEGER,
        is_from_me INTEGER,
        handle_id INTEGER
    )
    """)
    
    cursor.execute("""
    CREATE TABLE chat_message_join (
        chat_id INTEGER,
        message_id INTEGER
    )
    """)
    
    # Insert sample data
    # Chat 1: with "alice@example.com"
    cursor.execute("INSERT INTO handle (id) VALUES (?)", ("alice@example.com",))
    alice_handle_id = cursor.lastrowid
    
    cursor.execute("INSERT INTO chat (chat_identifier, display_name) VALUES (?, ?)", ("alice@example.com", "Alice"))
    chat_id_1 = cursor.lastrowid
    
    # Messages for Chat 1
    # Message 1: From Alice, yesterday
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    cocoa_epoch = datetime.datetime(2001, 1, 1)
    date_val = int((yesterday - cocoa_epoch).total_seconds() * 1_000_000_000)
    
    cursor.execute("INSERT INTO message (text, date, is_from_me, handle_id) VALUES (?, ?, ?, ?)", 
                   ("Hello there!", date_val, 0, alice_handle_id))
    msg_id_1 = cursor.lastrowid
    cursor.execute("INSERT INTO chat_message_join (chat_id, message_id) VALUES (?, ?)", (chat_id_1, msg_id_1))
    
    # Message 2: From Me, today
    today = datetime.datetime.now()
    date_val = int((today - cocoa_epoch).total_seconds() * 1_000_000_000)
    
    cursor.execute("INSERT INTO message (text, date, is_from_me, handle_id) VALUES (?, ?, ?, ?)", 
                   ("Hi Alice!", date_val, 1, 0))
    msg_id_2 = cursor.lastrowid
    cursor.execute("INSERT INTO chat_message_join (chat_id, message_id) VALUES (?, ?)", (chat_id_1, msg_id_2))

    conn.commit()
    conn.close()
    print(f"Created dummy database at {db_path}")

if __name__ == "__main__":
    create_dummy_db("dummy_chat.db")
