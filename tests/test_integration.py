import pytest
import csv
import datetime
import os
import sqlite3
import zipfile
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


def test_integration_list_target_shows_recent_messages(dummy_db):
    result = runner.invoke(app, ["--db-path", dummy_db, "list", "alice@example.com"])
    assert result.exit_code == 0
    assert "Recent messages for Alice" in result.output
    assert "Hi Alice!" in result.output


def test_integration_view_target_paginates(dummy_db):
    first = runner.invoke(app, ["--db-path", dummy_db, "view", "alice@example.com", "--page-size", "1"])
    second = runner.invoke(app, ["--db-path", dummy_db, "view", "alice@example.com", "--page-size", "1", "--page", "2"])
    assert first.exit_code == 0 and "Hi Alice!" in first.output and "Hello there!" in second.output


def test_integration_search_date_range(dummy_db):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    result = runner.invoke(app, ["--db-path", dummy_db, "search", "--from", today, "--to", today])
    assert result.exit_code == 0
    assert "Hi Alice!" in result.output


def test_integration_search_text_and_date_range(dummy_db):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    result = runner.invoke(app, ["--db-path", dummy_db, "search", "Hi", "--from", today, "--to", today])
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


def test_integration_export_chat_search_filter(dummy_db, tmp_path):
    output_path = tmp_path / "filtered.yaml"
    result = runner.invoke(
        app,
        ["--db-path", dummy_db, "export", "alice@example.com", "--search", "Hi", "--output", str(output_path)],
    )
    with open(output_path, encoding="utf-8") as export_file:
        data = yaml.safe_load(export_file)
    assert result.exit_code == 0 and data["message_count"] == 1


def test_integration_export_chat_csv(dummy_db, tmp_path):
    output_path = tmp_path / "conversation.csv"
    result = runner.invoke(
        app,
        [
            "--db-path",
            dummy_db,
            "export",
            "alice@example.com",
            "--format",
            "csv",
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    with open(output_path, newline="", encoding="utf-8") as export_file:
        rows = list(csv.DictReader(export_file))
    assert len(rows) == 2
    assert rows[0]["chat_identifier"] == "alice@example.com"
    assert rows[0]["text"] == "Hi Alice!"


def test_integration_export_chat_xlsx(dummy_db, tmp_path):
    output_path = tmp_path / "conversation.xlsx"
    result = runner.invoke(
        app,
        [
            "--db-path",
            dummy_db,
            "export",
            "alice@example.com",
            "--format",
            "xlsx",
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    assert output_path.exists()
    with zipfile.ZipFile(output_path) as workbook:
        names = set(workbook.namelist())
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet3.xml" in names
        messages_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "Hi Alice!" in messages_xml
    assert "chat_identifier" in messages_xml


def test_integration_list_ambiguous_target_shows_options(dummy_db):
    conn = sqlite3.connect(dummy_db)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat (chat_identifier, display_name, service_name) VALUES (?, ?, ?)",
            ("alice.work@example.com", "Alice Work", "iMessage"),
        )
        conn.commit()
    finally:
        conn.close()

    result = runner.invoke(app, ["--db-path", dummy_db, "list", "alice"])
    assert result.exit_code == 1
    assert "Conversations matching 'alice'" in result.output
    assert "Alice Work" in result.output
    assert "More than one match found" in result.output


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
