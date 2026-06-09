# Architecture

## Module map

- `src/imessage_exporter/cli.py` owns the Typer command surface and terminal formatting.
- `src/imessage_exporter/core.py` owns chat lookup, message search, export payload assembly, and file writing.
- `src/imessage_exporter/database.py` owns SQLite connection setup for `chat.db`.
- `src/imessage_exporter/contacts.py` owns optional Contacts database lookup.
- `src/imessage_exporter/search_index.py` owns the local SQLite FTS search index.
- `src/imessage_exporter/utils.py` owns date conversion and small shared formatting primitives.

## Data flow

The CLI parses global options, opens the requested Messages database, calls core query functions, formats rows for terminal output, and closes the SQLite connection in the command scope. View and export commands resolve a target into one or more chats before applying shared message filters for text, exact dates, date ranges, pagination, and file output.

## Invariants

- The tool reads local macOS data only; it does not send message content to external services.
- Commands must close database connections after each command finishes.
- Target resolution must not guess when multiple contacts or conversations match.
- The public CLI exposes both `imsg` and `imessage-exporter` entrypoints for the same Typer app.
- Export without filters must include the whole resolved conversation; filters narrow the export only when explicitly supplied.
- Message date searches use explicit calendar-day bounds: `--date` for one day, or inclusive `--from` / `--to` ranges.

## Search index

`imsg index build` creates a private local SQLite FTS/BM25 index in the user cache directory unless `--index-path` is provided. `imsg semantic` reads only that local index and asks the user to build it when missing.
