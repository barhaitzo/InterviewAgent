# Interview Agent — Project Specification

## Purpose

A local, always-on agentic system that delivers one short concept refresher + one interview question daily via email, grounded in a personal crash course markdown document. Built as a learning project; intentionally kept simple and framework-free.

## Goals & Non-Goals

**Goals:**
- End-to-end working pipeline: knowledge → generation → delivery → memory
- Daily automated trigger via Windows Task Scheduler
- Grounded outputs (RAG over personal markdown doc)
- Sequential or randomised topic rotation with repeat-avoidance
- Zero paid LLM dependencies — fully local via Ollama
- Educational: user wants to *understand* what makes an agent

**Non-Goals:**
- Multi-step planning / complex agent loops
- Web search or external tool use
- Multi-document corpus
- UI / dashboard
- Production-grade reliability

## Architecture Overview

```
Windows Task Scheduler (daily triggers)
        ↓ fires
   powershell.exe -NonInteractive -Command "wsl.exe -d Ubuntu -e bash -lc '...'"
        ↓ runs
   ~/interview_agent/run_daily.sh
        ↓ activates venv, runs
   python run_daily.py
        ↓ talks to
   Ollama on Windows host (http://localhost:11434)
        ↓ reads/writes
   ChromaDB (vectors) + SQLite (history) — both in WSL filesystem
        ↓ sends via
   smtplib → Gmail SMTP
```

**Key separation:** Windows handles scheduling only. WSL Ubuntu handles everything else.

## Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| OS | WSL2 Ubuntu | Linux dev ergonomics; faster filesystem for SQLite/Chroma |
| Language | Python 3.11+ | |
| LLM runtime | Ollama (on Windows host) | Already installed; reachable from WSL via `localhost:11434` |
| Generation model | `llama3.1:8b` | Strong instruction following, good tool-calling |
| Embedding model | `nomic-embed-text` | Free, local, solid quality |
| Vector store | ChromaDB | File-based, zero-config, SQLite-backed |
| History store | SQLite (stdlib `sqlite3`) | No deps, sufficient for this scale |
| Email | `smtplib` + Gmail App Password | Free, ~5 min setup |
| Scheduler | Windows Task Scheduler | Native, reliable, fires WSL |

## File Layout

```
~/interview_agent/
  config.py                # all tunable settings
  run_daily.py             # orchestrator (--dry-run flag available)
  run_daily.sh             # bash entry point invoked by Task Scheduler
  pytest.ini               # registers pytest markers
  .env                     # SMTP creds, never commit
  .gitignore
  requirements.txt

  pipeline/
    ingest.py              # markdown → chunks → ChromaDB
    agent.py               # agentic retrieve + generate + parse
    memory.py              # SQLite read/write, topic rotation
    email_sender.py        # SMTP delivery

  data/
    <your-course>.md       # source document (swap to change topic)

  storage/                 # auto-created at runtime, gitignored
    chroma_db/             # vector store
    history.db             # topic history

  logs/
    run.log                # appended on every run

  tests/
    conftest.py
    test_ingest.py
    test_agent.py
    test_memory.py
    test_email_sender.py
    test_run_daily.py
    test_e2e.py            # live integration tests (opt-in)

  docs/
    PROJECT_SPEC.md        # this file
```

## Configuration

All settings in `config.py`. Only `COURSE_NAME` needs to change when swapping courses — the others are either static tuning knobs or derived automatically.

```python
OLLAMA_BASE_URL = "http://localhost:11434"
GEN_MODEL = "llama3.1:8b"
EMBED_MODEL = "nomic-embed-text"
AGENTIC = True
MAX_TOOL_CALLS = 5

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3

RECENCY_DAYS = 14
SEQUENTIAL_LEARNING = True

COURSE_NAME = "..."                          # set this — drives the two below
COLLECTION_NAME = <slugified from COURSE_NAME>
SOURCE_DOC = Path(f"./data/{COLLECTION_NAME}.md")

CHROMA_PATH = Path("./storage/chroma_db")
HISTORY_DB_PATH = Path("./storage/history.db")
LOG_PATH = Path("./logs/run.log")
```

`.env`:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
EMAIL_TO=your_email@gmail.com
```

## Data Schemas

### ChromaDB collection

Each chunk stored with:
- `id`: stable hash of (heading_path + chunk_index)
- `embedding`: from `nomic-embed-text`
- `document`: chunk text
- `metadata`:
  - `topic`: top-level or second-level heading
  - `heading_path`: full path, e.g. `"Caching > Eviction Policies"`
  - `chunk_index`: position within section
  - `source`: filename

### SQLite: `history.db`

```sql
CREATE TABLE sent_anecdotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,           -- ISO 8601 UTC
    topic TEXT NOT NULL,
    chunk_ids_used TEXT NOT NULL,      -- JSON array of ChromaDB ids
    anecdote_text TEXT NOT NULL,
    question_text TEXT NOT NULL,
    model_used TEXT NOT NULL
);

CREATE INDEX idx_topic_timestamp ON sent_anecdotes(topic, timestamp);
```

## Daily Run Flow

```
1. Load all distinct topics from ChromaDB metadata
2. Sequential mode: advance past last-sent topic (wraps around)
   Random mode: query SQLite for topics covered within RECENCY_DAYS
               available = all_topics - recent; fall back to LRU if empty
3. Agent agentic loop: LLM calls retrieve() 1–3 times to gather chunks
4. Generate JSON {anecdote, question} grounded in retrieved content
5. Validate output with Pydantic; retry once with format enforcement on failure
6. Send email via Gmail SMTP
7. Log run to SQLite (topic, chunk_ids, generated text, model)
8. Append summary to logs/run.log
```

## Windows Task Scheduler Setup

**Action:**
- Program: `powershell.exe`
- Arguments: `-NonInteractive -Command "wsl.exe -d Ubuntu -e bash -lc 'cd /home/<username>/interview_agent && ./run_daily.sh'"`

**Triggers:** Daily at 10:00 and 14:00 (or as preferred).

**Settings:**
- "Run only when user is logged on" (WSL requires an active user session)
- "Stop the task if it runs longer than 10 minutes"
- "If the task is already running: Do not start a new instance"

`run_daily.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
{
  echo "=== Run started: $(date -Iseconds) ==="
  source .venv/bin/activate
  python run_daily.py
  echo "=== Run finished: $(date -Iseconds) ==="
  echo
} 2>&1 | tee -a logs/run.log
```

## Out of Scope

- Multiple source documents
- Web UI
- Difficulty calibration / spaced repetition
- Reply-to-email feedback loop
- Multi-step agent reasoning
