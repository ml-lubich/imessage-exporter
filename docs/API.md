# API

## Entrypoints

The package installs two equivalent console scripts:

- `imsg`
- `imessage-exporter`

Both execute `imessage_exporter.cli:main`.

## Global options

- `-h`, `--help`: show the help page and exit.
- `--db-path PATH`: read a specific Messages `chat.db` file.
- `--contacts-db-path PATH`: read a specific Contacts `.abcddb` database; repeatable.

## Commands

- `imsg list [TARGET] --limit N`: list recent chats or recent messages for one resolved target.
- `imsg find QUERY --limit N`: find matching contacts and conversations.
- `imsg view TARGET --page N --page-size N --search TEXT --date YYYY-MM-DD --from YYYY-MM-DD --to YYYY-MM-DD --output PATH --format FORMAT`: page through one resolved conversation and optionally export all matching messages.
- `imsg search [QUERY] --limit N --date YYYY-MM-DD`: search messages on one calendar date.
- `imsg search [QUERY] --limit N --from YYYY-MM-DD --to YYYY-MM-DD`: search messages within an inclusive calendar-day range.
- `imsg export TARGET --output PATH --format FORMAT --limit N --include-groups --search TEXT --date YYYY-MM-DD --from YYYY-MM-DD --to YYYY-MM-DD`: export messages for a resolved target.
- `imsg index build --index-path PATH`: build the local all-message search index.
- `imsg index status --index-path PATH`: inspect the local search index.
- `imsg semantic QUERY --limit N --index-path PATH`: search the local index.

## Export formats

Supported export formats are `yaml`, `json`, `csv`, and `xlsx`. YAML and JSON preserve the nested export payload; CSV emits message rows; XLSX emits workbook sheets for messages, conversations, and daily counts.

## Message filters

The `search` text argument is optional when a date filter is provided. Use `--date` by itself for one day, or combine `--from` and `--to` for a range; `--to` includes the full calendar day by querying before the next day. Text and date filters can be combined in `search`, `view`, and `export`; do not combine `--date` with `--from` or `--to`.

## View pagination

`imsg view TARGET` shows one page of messages for a resolved conversation. Page 1 is the newest page, `--page-size` controls the page length, and `--output` writes all matching messages for the same filters rather than only the current page.

## Exit codes

- `0`: command completed successfully or help was shown.
- `1`: user-actionable failure such as no target match, ambiguous target, invalid date, missing index, or database access failure.

## Permissions

The terminal or IDE running the command needs macOS Full Disk Access when reading the real `~/Library/Messages/chat.db` database.
