# Runbook

## Setup

1. Install uv if it is not already available.
2. From the repository root, run `uv sync --dev`.
3. Grant Full Disk Access to the terminal or IDE that will run the CLI when using the real Messages database.

## Run locally

Use the short entrypoint for daily work:

```bash
uv run imsg -h
uv run imsg list
uv run imsg view alice@example.com --page-size 25
uv run imsg search hello
uv run imsg search --from 2026-06-01 --to 2026-06-08
uv run imsg search meeting --from 2026-06-01 --to 2026-06-08
```

Use `--db-path` with a fixture or copied database when testing without the live macOS Messages store.

## Common failures

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `unable to open database file` | Missing Full Disk Access or wrong `chat.db` path | Grant Full Disk Access or pass `--db-path` |
| `No search index found yet` | `imsg semantic` ran before indexing | Run `imsg index build` |
| `Invalid date format` | Date is not `YYYY-MM-DD` | Re-run with an ISO date |
| Multiple matches printed | Target is ambiguous | Use a chat ID, phone, email, or more specific name |
| `ModuleNotFoundError: No module named 'textual'` | `imsg` tool env is stale after adding a new dep | Run `uv tool install --editable . --force` from repo root |

## Message search workflow

Use `imsg search [QUERY] --date YYYY-MM-DD` for one calendar day. Use `imsg search [QUERY] --from YYYY-MM-DD --to YYYY-MM-DD` for inclusive calendar-day ranges; omit `QUERY` for date-only browsing.

## Installing / upgrading the global tool

After cloning or pulling new deps, reinstall the tool env:

```bash
uv tool install --editable . --force
```

## View and export workflow

Start with `imsg find NAME` when the exact target is unknown, then run `imsg view TARGET` to open the interactive TUI (arrow keys navigate pages, q quits). Run `imsg export TARGET` for a full conversation dump. Add `--search`, `--date`, or `--from`/`--to` to `view` or `export` for filtered slices.

## Search index maintenance

Rebuild the local index whenever newly arrived messages should be searchable by `imsg semantic`. The default index path is under `~/Library/Caches/imessage-exporter/`.

## Credential rotation

This project does not require API keys or external credentials. macOS privacy permissions are managed in System Settings under Privacy & Security.
