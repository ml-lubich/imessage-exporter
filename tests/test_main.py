import pytest
import sys
import datetime
import sqlite3
from unittest.mock import MagicMock, patch, call
from imessage_exporter.main import IMessageExporter, main, COCOA_EPOCH

# --- Fixtures ---

@pytest.fixture
def mock_db_path(tmp_path):
    # Create a dummy file so os.path.exists returns True
    db_file = tmp_path / "chat.db"
    db_file.touch()
    return str(db_file)

@pytest.fixture
def exporter(mock_db_path):
    return IMessageExporter(db_path=mock_db_path)

# --- Tests ---

def test_connect_success(exporter):
    with patch("sqlite3.connect") as mock_connect:
        exporter.connect()
        mock_connect.assert_called_once()
        assert exporter.conn is not None

def test_connect_file_not_found():
    exporter = IMessageExporter(db_path="/non/existent/path.db")
    with pytest.raises(FileNotFoundError):
        exporter.connect()

def test_connect_operational_error(exporter):
    with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("perms")):
        with patch("sys.exit") as mock_exit:
            exporter.connect()
            mock_exit.assert_called_once_with(1)

def test_cocoa_to_datetime(exporter):
    # 0 nanoseconds = 2001-01-01
    assert exporter._cocoa_to_datetime(0) == COCOA_EPOCH
    # None input
    assert exporter._cocoa_to_datetime(None) is None
    # Invalid input
    assert exporter._cocoa_to_datetime("invalid") is None
    # 1 second after epoch (1 billion ns)
    expected = COCOA_EPOCH + datetime.timedelta(seconds=1)
    assert exporter._cocoa_to_datetime(1_000_000_000) == expected

def test_list_chats(exporter):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    exporter.conn = mock_conn

    # Mock data: ROWID, chat_identifier, display_name, last_msg_date
    data = [
        {"ROWID": 1, "chat_identifier": "user@example.com", "display_name": "User", "last_msg_date": 0},
        {"ROWID": 2, "chat_identifier": "unknown", "display_name": None, "last_msg_date": None}
    ]
    mock_cursor.__iter__.return_value = iter(data)

    with patch("builtins.print") as mock_print:
        exporter.list_chats()
        
        # Verify query execution
        mock_cursor.execute.assert_called_once()
        
        # Verify output contains expected strings
        # We can check if print was called with our data
        print_calls = [str(c) for c in mock_print.mock_calls]
        assert any("User" in c for c in print_calls)
        assert any("unknown" in c for c in print_calls)

def test_search_messages_basic(exporter):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    exporter.conn = mock_conn

    exporter.search_messages(search_term="hello")
    
    # Verify query contains LIKE clause
    args, _ = mock_cursor.execute.call_args
    query = args[0]
    params = args[1]
    assert "LIKE ?" in query
    assert "%hello%" in params

def test_search_messages_today(exporter):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    exporter.conn = mock_conn

    exporter.search_messages(date_filter="today")
    
    args, _ = mock_cursor.execute.call_args
    query = args[0]
    assert "message.date >= ?" in query

def test_search_messages_specific_date(exporter):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    exporter.conn = mock_conn

    exporter.search_messages(specific_date="2023-10-27")
    
    args, _ = mock_cursor.execute.call_args
    query = args[0]
    assert "message.date >= ?" in query
    assert "message.date < ?" in query

def test_search_messages_invalid_date(exporter):
    with patch("builtins.print") as mock_print:
        exporter.search_messages(specific_date="invalid-date")
        mock_print.assert_called_with("Invalid date format. Please use YYYY-MM-DD")

def test_main_cli_list_chats():
    with patch("sys.argv", ["imessage-exporter", "--list-chats"]):
        with patch("imessage_exporter.main.IMessageExporter") as MockExporter:
            mock_instance = MockExporter.return_value
            main()
            mock_instance.connect.assert_called_once()
            mock_instance.list_chats.assert_called_once()
            mock_instance.close.assert_called_once()

def test_main_cli_search():
    with patch("sys.argv", ["imessage-exporter", "--search", "test"]):
        with patch("imessage_exporter.main.IMessageExporter") as MockExporter:
            mock_instance = MockExporter.return_value
            main()
            mock_instance.search_messages.assert_called_once_with("test", None, None)

def test_main_cli_no_args():
    with patch("sys.argv", ["imessage-exporter"]):
        with patch("imessage_exporter.main.IMessageExporter") as MockExporter:
            with patch("argparse.ArgumentParser.print_help") as mock_help:
                main()
                mock_help.assert_called_once()
