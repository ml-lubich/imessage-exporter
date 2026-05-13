# iMessage Exporter

> A Python tool to search and export iMessages from your local macOS
> `chat.db`.

```mermaid
flowchart LR
    USER[("👤 you<br/>Terminal · IDE")]
    CLI{{"🧰 imessage-exporter<br/>CLI"}}
    FLAGS["🎚 flags<br/>--search · --today · --date · --list-chats"]
    DB[("🗄 ~/Library/Messages<br/>chat.db<br/>(needs Full Disk Access)")]
    QUERY["🔍 SQL filter<br/>by date / text"]
    OUT[/"📄 stdout<br/>messages · chat list"/]

    USER --> CLI --> FLAGS --> QUERY
    QUERY --> DB
    DB --> QUERY --> OUT

    classDef io fill:#0e1116,stroke:#2f81f7,stroke-width:1.5px,color:#e6edf3;
    classDef tool fill:#161b22,stroke:#3fb950,stroke-width:1.5px,color:#e6edf3;
    classDef brain fill:#161b22,stroke:#d29922,stroke-width:1.5px,color:#e6edf3;
    classDef out fill:#0e1116,stroke:#a371f7,stroke-width:1.5px,color:#e6edf3;
    class USER,DB io;
    class FLAGS,QUERY tool;
    class CLI brain;
    class OUT out;
```

## Table of contents

- [Installation](#installation)
- [Usage](#usage)
- [Permissions](#permissions)

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
