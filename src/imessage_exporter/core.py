import sqlite3
import datetime
from typing import Optional
from .utils import cocoa_to_datetime, COCOA_EPOCH

def list_chats(conn: sqlite3.Connection, limit: int = 50):
    """List recent chat sessions."""
    query = """
    SELECT 
        chat.ROWID, 
        chat.chat_identifier, 
        chat.display_name,
        MAX(message.date) as last_msg_date
    FROM chat
    LEFT JOIN chat_message_join ON chat.ROWID = chat_message_join.chat_id
    LEFT JOIN message ON chat_message_join.message_id = message.ROWID
    GROUP BY chat.ROWID
    ORDER BY last_msg_date DESC
    LIMIT ?
    """
    cursor = conn.cursor()
    try:
        cursor.execute(query, (limit,))
        print(f"{'ID':<5} | {'Identifier':<30} | {'Last Activity':<20}")
        print("-" * 60)
        for row in cursor:
            date_val = cocoa_to_datetime(row['last_msg_date'])
            date_str = date_val.strftime('%Y-%m-%d %H:%M') if date_val else "N/A"
            ident = row['chat_identifier'] or "Unknown"
            display = row['display_name'] or ident
            print(f"{row['ROWID']:<5} | {display[:30]:<30} | {date_str:<20}")
    except sqlite3.Error as e:
        print(f"Database error: {e}")

def search_messages(conn: sqlite3.Connection, search_term: Optional[str] = None, date_filter: Optional[str] = None, specific_date: Optional[str] = None):
    """Search and print messages based on filters."""
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

    if date_filter == 'today':
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
            print("Invalid date format. Please use YYYY-MM-DD")
            return

    query += " ORDER BY message.date ASC"

    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        print(f"Found {len(rows)} messages.")
        print("-" * 80)
        
        for row in rows:
            date_val = cocoa_to_datetime(row['date'])
            date_str = date_val.strftime('%Y-%m-%d %H:%M:%S') if date_val else "Unknown Date"
            sender = "Me" if row['is_from_me'] else (row['handle_id'] or "Unknown")
            text = row['text']
            
            print(f"[{date_str}] {sender}: {text}")
            print("-" * 40)
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
