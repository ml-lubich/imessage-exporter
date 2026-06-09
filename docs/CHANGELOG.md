# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [0.4.0] - 2026-06-08

### Added

- `imsg view` now launches a full interactive Textual TUI: arrow keys (← →) and h/l navigate pages, q quits.
- All messages are loaded upfront and paginated in-memory; no `--page` flag needed.

### Changed

- Removed `--page` and `--all` flags from `imsg view`; the TUI handles all navigation.
- `--page-size` controls TUI page size (default 10).
- Bumped `requires-python` to `>=3.9` (textual requirement).

## [0.3.0] - 2026-06-08

### Changed

- Added `imsg view` for paginated conversation browsing with optional text/date filters and export output.
- Added `--search`, `--date`, `--from`, and `--to` filters to `imsg export` while preserving full conversation export by default.
- Removed the `imsg today` command and replaced it with `imsg search` date filters for exact dates, inclusive date ranges, and text-plus-range queries.
- Added `-h` as a short alias for the CLI help page alongside `--help`.
- Added canonical engineering docs for architecture, API, testing, and operations.

## [0.2.0] - 2026-06-08

### Added

- Added indexed local message search with `imsg index` and `imsg semantic`.
