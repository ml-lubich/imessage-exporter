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
- [Query flow (sequence)](#query-flow-sequence)
- [Filter algorithm](#filter-algorithm)
- [Usage](#usage)
- [Permissions](#permissions)
- [🗺️ Repository map](#️-repository-map)
- [📊 Code composition](#-code-composition)

## Filter algorithm

```mermaid
flowchart LR
    A([CLI flags])
    B{"--list-chats?"}
    C["SELECT chats"]
    D{"--today?"}
    E["date >= today 00:00"]
    F{"--date YYYY-MM-DD?"}
    G["date in [d, d+1)"]
    H{"--search TEXT?"}
    I["text LIKE %TEXT%"]
    J["compose WHERE"]
    K["SELECT m.text, h.id, m.date"]
    L["format rows"]
    Z([stdout])
    A --> B
    B -- yes --> C --> Z
    B -- no  --> D
    D -- yes --> E --> J
    D -- no  --> F
    F -- yes --> G --> J
    F -- no  --> J
    J --> H
    H -- yes --> I --> K
    H -- no  --> K
    K --> L --> Z
```

## Query flow (sequence)

```mermaid
sequenceDiagram
    participant U as user
    participant CLI as imessage-exporter
    participant P as arg parser
    participant Q as SQL builder
    participant DB as chat.db (SQLite)

    U->>CLI: --search hello --today
    CLI->>P: parse flags
    P->>Q: build WHERE clauses<br/>(date range, LIKE)
    Q->>DB: SELECT m.text, h.id, m.date<br/>FROM message m JOIN handle h
    DB-->>Q: rows
    Q-->>CLI: format records
    CLI-->>U: stdout (matched messages)
```

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


## 🗺️ Repository map

Top-level layout of `imessage-exporter` rendered as a Mermaid mindmap (auto-generated from the on-disk tree).

```mermaid
mindmap
  root((imessage-exporter))
    src/
      imessage_exporter
    tests/
      create_dummy_db.py
      test_integration.py
      test_unit.py
    files
      README.md
      pyproject.toml
```


## 📊 Code composition

File-type breakdown of source under this repo (skips `.git`, `node_modules`, build caches, lockfiles).

```mermaid
pie showData title File-type composition of imessage-exporter (10 files)
    "Python" : 8
    "TOML" : 1
    "Markdown" : 1
```
