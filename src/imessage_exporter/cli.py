import argparse
import sys
from .database import get_db_connection, CHAT_DB_PATH
from .core import list_chats, search_messages

def main():
    parser = argparse.ArgumentParser(description="Export and search iMessages.")
    parser.add_argument("--search", help="Search term for messages")
    parser.add_argument("--list-chats", action="store_true", help="List recent chats")
    parser.add_argument("--today", action="store_true", help="Filter for messages from today")
    parser.add_argument("--date", help="Filter by specific date (YYYY-MM-DD)")
    parser.add_argument("--db-path", default=CHAT_DB_PATH, help="Path to chat.db (default: ~/Library/Messages/chat.db)")
    
    args = parser.parse_args()

    try:
        conn = get_db_connection(args.db_path)
    except Exception as e:
        print(f"Error: {e}")
        print("Please ensure you have granted Full Disk Access to your terminal/IDE.")
        sys.exit(1)

    try:
        if args.list_chats:
            list_chats(conn)
        elif args.search or args.today or args.date:
            search_messages(conn, args.search, 'today' if args.today else None, args.date)
        else:
            parser.print_help()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
