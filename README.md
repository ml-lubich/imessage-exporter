# iMessage Exporter

A Python tool to search and export iMessages from your local macOS `chat.db`.

## Installation

1. Clone this repository.
2. Install in editable mode:
   ```bash
   pip install -e .
   ```

## Usage

The tool provides a CLI command `imessage-exporter`.

### List Recent Chats
```bash
imessage-exporter --list-chats
```

### Search Messages
Search for a specific term:
```bash
imessage-exporter --search "hello"
```

### Filter by Date
Get messages from today:
```bash
imessage-exporter --today
```

Get messages from a specific date:
```bash
imessage-exporter --date 2023-10-27
```

### Combine Filters
Search for "meeting" in messages from today:
```bash
imessage-exporter --search "meeting" --today
```

## Permissions

This tool requires **Full Disk Access** for the terminal or IDE running it, as it reads directly from `~/Library/Messages/chat.db`.
