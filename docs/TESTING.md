# Testing

## Verification commands

Run the test suite from the repository root with uv:

```bash
uv run pytest
```

For a fast targeted CLI check, run:

```bash
uv run pytest tests/test_unit.py::test_main_cli_short_help_alias
```

## Definition of Done

- Unit tests cover pure conversion, database connection behavior, core query construction, and CLI command dispatch.
- Integration tests create a real temporary SQLite fixture and verify list, paginated view, text search, date-range search, filtered export, index, and semantic paths.
- File-writing paths write real YAML, CSV, and XLSX files under pytest temporary directories.
- Help behavior must keep both `-h` and `--help` working for the CLI surface.

## Negative fixtures

- Missing database paths raise `FileNotFoundError`.
- Invalid dates produce a user-facing error.
- Missing search indexes produce a user-facing instruction to run `imsg index build`.
- Ambiguous targets print candidate conversations instead of selecting one silently.

## Not tested intentionally

The suite does not read the user's real Messages or Contacts databases. Real macOS Full Disk Access behavior is verified manually because it depends on host privacy settings.
