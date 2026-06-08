import pytest
import os
import yaml
from typer.testing import CliRunner
from imessage_exporter.cli import app
from create_dummy_db import create_dummy_db

runner = CliRunner()

@pytest.fixture(scope="function")
def dummy_db(tmp_path):
    db_path = tmp_path / "test_chat.db"
    create_dummy_db(str(db_path))
    yield str(db_path)
    # Cleanup handled by tmp_path, but explicit removal is fine too
    if os.path.exists(db_path):
        os.remove(db_path)

def test_integration_list_chats(dummy_db):
    result = runner.invoke(app, ["--db-path", dummy_db, "list"])
    assert result.exit_code == 0
    assert "Alice" in result.output

def test_integration_search_today(dummy_db):
    # Message 2 is from today: "Hi Alice!"
    result = runner.invoke(app, ["--db-path", dummy_db, "today", "Hi"])
    assert result.exit_code == 0
    assert "Hi Alice!" in result.output
    assert "Me" in result.output

def test_integration_search_history(dummy_db):
    # Message 1 is from yesterday: "Hello there!"
    result = runner.invoke(app, ["--db-path", dummy_db, "search", "Hello"])
    assert result.exit_code == 0
    assert "Hello there!" in result.output
    assert "alice@example.com" in result.output

def test_integration_export_chat_yaml(dummy_db, tmp_path):
    output_path = tmp_path / "conversation.yaml"
    result = runner.invoke(
        app,
        [
            "--db-path",
            dummy_db,
            "export",
            "alice@example.com",
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    with open(output_path, encoding="utf-8") as export_file:
        data = yaml.safe_load(export_file)
    assert data["conversation_count"] == 1
    assert data["message_count"] == 2
    assert data["conversations"][0]["chat"]["identifier"] == "alice@example.com"
    assert data["conversations"][0]["messages"][0]["text"] == "Hi Alice!"


def test_integration_index_and_semantic_search(dummy_db, tmp_path):
    index_path = tmp_path / "messages.sqlite"

    build_result = runner.invoke(
        app,
        [
            "--db-path",
            dummy_db,
            "index",
            "build",
            "--index-path",
            str(index_path),
        ],
    )
    assert build_result.exit_code == 0
    assert "Indexed 2 messages" in build_result.output
    assert index_path.exists()

    status_result = runner.invoke(
        app,
        ["index", "status", "--index-path", str(index_path)],
    )
    assert status_result.exit_code == 0
    assert "message_count" in status_result.output
    assert "2" in status_result.output

    search_result = runner.invoke(
        app,
        ["semantic", "Hello", "--index-path", str(index_path)],
    )
    assert search_result.exit_code == 0
    assert "Hello there!" in search_result.output
    assert "Alice" in search_result.output


def test_integration_semantic_search_requires_index(tmp_path):
    index_path = tmp_path / "missing.sqlite"
    result = runner.invoke(
        app,
        ["semantic", "Hello", "--index-path", str(index_path)],
    )
    assert result.exit_code == 1
    assert "No search index found yet" in result.output
    assert not index_path.exists()
