import pytest
import sys
import datetime
import sqlite3
from unittest.mock import MagicMock, patch, call
from imessage_exporter.cli import main
from imessage_exporter.core import list_chats, search_messages
from imessage_exporter.database import get_db_connection
from imessage_exporter.utils import cocoa_to_datetime, COCOA_EPOCH

# --- Utils Tests ---

def test_cocoa_to_datetime():
    # 0 nanoseconds = 2001-01-01
    assert cocoa_to_datetime(0) == COCOA_EPOCH
    # None input
    assert cocoa_to_datetime(None) is None
    # Invalid input
    assert cocoa_to_datetime("invalid") is None
    # 1 second after epoch (1 billion ns)
    expected = COCOA_EPOCH + datetime.timedelta(seconds=1)
    assert cocoa_to_datetime(1_000_000_000) == expected

# --- Database Tests ---

def test_get_db_connection_success(tmp_path):
    db_file = tmp_path / "chat.db"
    db_file.touch()
    with patch("sqlite3.connect") as mock_connect:
        conn = get_db_connection(str(db_file))
        mock_connect.assert_called_once()
        assert conn is not None

def test_get_db_connection_file_not_found():
    with pytest.raises(FileNotFoundError):
        get_db_connection("/non/existent/path.db")

# --- Core Tests ---

def test_list_chats():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    
    # Mock data: ROWID, chat_identifier, display_name, last_msg_date
    data = [
        {"ROWID": 1, "chat_identifier": "user@example.com", "display_name": "User", "last_msg_date": 0},
        {"ROWID": 2, "chat_identifier": "unknown", "display_name": None, "last_msg_date": None}
    ]
    mock_cursor.__iter__.return_value = iter(data)

    with patch("builtins.print") as mock_print:
        list_chats(mock_conn)
        
        # Verify query execution
        mock_cursor.execute.assert_called_once()
        
        # Verify output contains expected strings
        print_calls = [str(c) for c in mock_print.mock_calls]
        assert any("User" in c for c in print_calls)
        assert any("unknown" in c for c in print_calls)

def test_search_messages_basic():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    search_messages(mock_conn, search_term="hello")
    
    # Verify query contains LIKE clause
    args, _ = mock_cursor.execute.call_args
    query = args[0]
    params = args[1]
    assert "LIKE ?" in query
    assert "%hello%" in params

def test_search_messages_today():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    search_messages(mock_conn, date_filter="today")
    
    args, _ = mock_cursor.execute.call_args
    query = args[0]
    assert "message.date >= ?" in query

def test_search_messages_specific_date():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    search_messages(mock_conn, specific_date="2023-10-27")
    
    args, _ = mock_cursor.execute.call_args
    query = args[0]
    assert "message.date >= ?" in query
    assert "message.date < ?" in query

def test_search_messages_invalid_date():
    mock_conn = MagicMock()
    with patch("builtins.print") as mock_print:
        search_messages(mock_conn, specific_date="invalid-date")
        mock_print.assert_called_with("Invalid date format. Please use YYYY-MM-DD")

# --- CLI Tests ---

def test_main_cli_list_chats():
    with patch("sys.argv", ["imessage-exporter", "--list-chats"]):
        with patch("imessage_exporter.cli.get_db_connection") as mock_connect:
            with patch("imessage_exporter.cli.list_chats") as mock_list:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn
                main()
                mock_connect.assert_called_once()
                mock_list.assert_called_once()
                mock_conn.close.assert_called_once()

def test_main_cli_search():
    with patch("sys.argv", ["imessage-exporter", "--search", "test"]):
        with patch("imessage_exporter.cli.get_db_connection") as mock_connect:
            with patch("imessage_exporter.cli.search_messages") as mock_search:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn
                main()
                mock_search.assert_called_once_with(mock_conn, "test", None, None)

    with patch("sys.argv", ["imessage-exporter"]):
        with patch("imessage_exporter.cli.get_db_connection") as mock_connect:
             with patch("argparse.ArgumentParser.print_help") as mock_help:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn
                main()
                mock_help.assert_called_once()

# --- Edge Case Tests ---

def test_search_messages_sql_injection():
    """Ensure search term is parameterized and not vulnerable to injection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    # Attempt injection
    search_messages(mock_conn, search_term="'; DROP TABLE message; --")
    
    args, _ = mock_cursor.execute.call_args
    query = args[0]
    params = args[1]
    
    # Should still use parameter binding
    assert "LIKE ?" in query
    assert "DROP TABLE" not in query # The injection string should not be part of the SQL
    assert "%'; DROP TABLE message; --%" in params # It should be in the params

def test_list_chats_empty_db():
    """Handle empty database gracefully."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.__iter__.return_value = iter([]) # Empty result

    with patch("builtins.print") as mock_print:
        list_chats(mock_conn)
        # Should print header but no rows
        # We can verify it didn't crash
        assert mock_print.call_count >= 2 # Header lines

def test_get_db_connection_permission_error():
    """Simulate permission error (e.g. no Full Disk Access)."""
    with patch("os.path.exists", return_value=True):
        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("unable to open database file")):
            with pytest.raises(sqlite3.OperationalError):
                get_db_connection("protected.db")

def test_cocoa_to_datetime_negative():
    """Handle dates before 2001-01-01."""
    # -1 second
    dt = cocoa_to_datetime(-1_000_000_000)
    expected = COCOA_EPOCH - datetime.timedelta(seconds=1)
    assert dt == expected

