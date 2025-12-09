import pytest
import os
import sys
from unittest.mock import patch
from io import StringIO
from imessage_exporter.cli import main
from tests.create_dummy_db import create_dummy_db

@pytest.fixture(scope="function")
def dummy_db(tmp_path):
    db_path = tmp_path / "test_chat.db"
    create_dummy_db(str(db_path))
    yield str(db_path)
    # Cleanup handled by tmp_path, but explicit removal is fine too
    if os.path.exists(db_path):
        os.remove(db_path)

def test_integration_list_chats(dummy_db):
    with patch("sys.argv", ["imessage-exporter", "--list-chats", "--db-path", dummy_db]):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main()
            output = fake_out.getvalue()
            assert "Alice" in output
            # assert "alice@example.com" in output # Display name takes precedence

def test_integration_search_today(dummy_db):
    # Message 2 is from today: "Hi Alice!"
    with patch("sys.argv", ["imessage-exporter", "--search", "Hi", "--today", "--db-path", dummy_db]):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main()
            output = fake_out.getvalue()
            assert "Hi Alice!" in output
            assert "Me:" in output

def test_integration_search_history(dummy_db):
    # Message 1 is from yesterday: "Hello there!"
    with patch("sys.argv", ["imessage-exporter", "--search", "Hello", "--db-path", dummy_db]):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main()
            output = fake_out.getvalue()
            assert "Hello there!" in output
            assert "alice@example.com" in output
