import sqlite3
import argparse
import os
import sys
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Constants
CHAT_DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
COCOA_EPOCH = datetime.datetime(2001, 1, 1, 0, 0, 0)

class IMessageExporter:
    def __init__(self, db_path: str = CHAT_DB_PATH):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found at {self.db_path}")
        
        try:
            # Open in read-only mode with URI
            self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            self.conn.row_factory = sqlite3.Row
        except sqlite3.OperationalError as e:
            print(f"Error opening database: {e}")
            print("Please ensure you have granted Full Disk Access to your terminal/IDE.")
            sys.exit(1)

    def close(self):
        if self.conn:
            self.conn.close()

    def _cocoa_to_datetime(self, nanoseconds: Optional[int]) -> Optional[datetime.datetime]:
        if nanoseconds is None:
            return None
        try:
            seconds = nanoseconds / 1_000_000_000
            return COCOA_EPOCH + datetime.timedelta(seconds=seconds)
        except Exception:
            return None

    def list_chats(self, limit: int = 50):
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
        cursor = self.conn.cursor()
        try:
            cursor.execute(query, (limit,))
            print(f"{'ID':<5} | {'Identifier':<30} | {'Last Activity':<20}")
            print("-" * 60)
            for row in cursor:
                date_val = self._cocoa_to_datetime(row['last_msg_date'])
                date_str = date_val.strftime('%Y-%m-%d %H:%M') if date_val else "N/A"
                ident = row['chat_identifier'] or "Unknown"
                # Handle potential None display_name
                display = row['display_name'] or ident
                print(f"{row['ROWID']:<5} | {display[:30]:<30} | {date_str:<20}")
        except sqlite3.Error as e:
            print(f"Database error: {e}")

    def search_messages(self, search_term: Optional[str] = None, date_filter: Optional[str] = None, specific_date: Optional[str] = None):
        # Optimized query to avoid joining everything if not needed, 
        # but we need handle and chat info for context.
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

        cursor = self.conn.cursor()
        try:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            print(f"Found {len(rows)} messages.")
            print("-" * 80)
            
            for row in rows:
                date_val = self._cocoa_to_datetime(row['date'])
                date_str = date_val.strftime('%Y-%m-%d %H:%M:%S') if date_val else "Unknown Date"
                sender = "Me" if row['is_from_me'] else (row['handle_id'] or "Unknown")
                text = row['text']
                
                print(f"[{date_str}] {sender}: {text}")
                print("-" * 40)
                
        except sqlite3.Error as e:
            print(f"Database error: {e}")

def main():
    parser = argparse.ArgumentParser(description="Export and search iMessages.")
    parser.add_argument("--search", help="Search term for messages")
    parser.add_argument("--list-chats", action="store_true", help="List recent chats")
    parser.add_argument("--today", action="store_true", help="Filter for messages from today")
    parser.add_argument("--date", help="Filter by specific date (YYYY-MM-DD)")
    
    args = parser.parse_args()

    exporter = IMessageExporter()
    exporter.connect()

    try:
        if args.list_chats:
            exporter.list_chats()
        elif args.search or args.today or args.date:
            exporter.search_messages(args.search, 'today' if args.today else None, args.date)
        else:
            parser.print_help()
    finally:
        exporter.close()

if __name__ == "__main__":
    main()
