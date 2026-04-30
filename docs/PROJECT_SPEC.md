# Interview Assistant Agent — Project Specification

## Purpose

A local, always-on agentic system that delivers one short concept refresher + one interview question daily via email, grounded in a personal ML system design crash course document. The first agentic project for the user; learning-oriented, kept intentionally simple.

## Goals & Non-Goals

**Goals:**
- End-to-end working pipeline: knowledge → generation → delivery → memory
- Daily automated trigger via Windows Task Scheduler
- Grounded outputs (RAG over personal markdown doc)
- Memory of past topics to avoid repetition
- Zero paid LLM dependencies — fully local via Ollama
- Educational: user wants to *understand* what makes an agent

**Non-Goals (for v1):**
- Multi-step planning / complex agent loops
- Web search or external tool use
- Multi-document corpus
- UI / dashboard
- Production-grade reliability

## Architecture Overview

```
Windows Task Scheduler (8am daily)
        ↓ fires
   wsl.exe -d Ubuntu -e bash -lc "..."
        ↓ runs
   ~/interview-agent/run_daily.sh
        ↓ activates venv, runs
   python run_daily.py
        ↓ talks to
   Ollama on Windows host (http://localhost:11434)
        ↓ reads/writes
   Chroma (vectors) + SQLite (history) — both in WSL filesystem
        ↓ sends via
   smtplib → Gmail SMTP
```

**Key separation:** Windows handles scheduling only. WSL Ubuntu handles everything else.

## Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| OS | WSL2 Ubuntu | Linux dev ergonomics; faster filesystem for SQLite |
| Language | Python 3.11+ | |
| LLM runtime | Ollama (on Windows host) | Already installed; reachable from WSL via `localhost:11434` |
| Generation model | `qwen2.5:7b` | Strong tool-calling, good instruction following |
| Embedding model | `nomic-embed-text` | Free, local, solid quality |
| Vector store | ChromaDB | File-based, zero-config, SQLite-backed |
| History store | SQLite (stdlib `sqlite3`) | No deps, sufficient for this scale |
| Email | `smtplib` + Gmail App Password | Free, ~5 min setup |
| Scheduler | Windows Task Scheduler | Native, reliable, fires WSL |

## Decisions Locked

1. **Anecdote style: option (c)** — concise concept refreshers framed memorably. NOT hypothetical scenarios, NOT war-stories with company names. Stays tightly grounded in the source doc; minimizes hallucination risk.
2. **Memory window:** 14 days default; revisit once we know the topic count after ingestion.
3. **Topic derivation:** Use markdown heading hierarchy (`#`, `##`, `###`) as natural topic boundaries. Each chunk tagged with its parent heading(s).
4. **Ollama location:** Windows host. WSL reaches it at `http://localhost:11434`. Don't install a second Ollama in WSL.
5. **Project location inside WSL:** `~/interview-agent/` on the Linux filesystem — NOT under `/mnt/c/`. Performance matters for Chroma.
6. **Agentic-ness for v1:** Pipeline, not loop. The "agentic upgrade" (LLM decides what to retrieve via tool calls) is a Day 3 milestone, not a v1 requirement.

## File Layout

```
~/interview-agent/
  PROJECT_SPEC.md          # this file
  CLAUDE.md                # working notes for Claude Code (separate doc)
  README.md                # human-facing setup notes (generate later)
  .env                     # SMTP creds, never commit
  .gitignore
  requirements.txt
  config.py                # constants: model names, paths, recency window
  ingest.py                # one-time: markdown → chunks → Chroma
  agent.py                 # generation logic (retrieve + prompt + parse)
  memory.py                # SQLite read/write for topic history
  send_email.py            # SMTP wrapper
  run_daily.py             # orchestrator
  run_daily.sh             # bash entry point invoked by Task Scheduler
  data/
    crash_course.md        # source document
  chroma_db/               # auto-created by Chroma
  history.db               # auto-created SQLite
  logs/
    run.log                # appended on every run
```

## Data Schemas

### Chroma collection: `crash_course`

Each chunk stored with:
- `id`: stable hash of (heading_path + chunk_index)
- `embedding`: from `nomic-embed-text`
- `document`: chunk text
- `metadata`:
  - `topic`: top-level or second-level heading (decide after seeing doc structure)
  - `heading_path`: full path, e.g. `"Sharding > Consistent Hashing"`
  - `chunk_index`: position within section
  - `source`: filename

### SQLite: `history.db`

```sql
CREATE TABLE sent_anecdotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,           -- ISO 8601
    topic TEXT NOT NULL,
    chunk_ids_used TEXT NOT NULL,      -- JSON array of Chroma ids
    anecdote_text TEXT NOT NULL,
    question_text TEXT NOT NULL,
    model_used TEXT NOT NULL
);

CREATE INDEX idx_topic_timestamp ON sent_anecdotes(topic, timestamp);
```

## Daily Run Flow

```
1. Load all distinct topics from Chroma metadata
2. Query SQLite: topics covered in last RECENCY_DAYS (default 14)
3. available_topics = all_topics - recent_topics
   - If empty (rare; full rotation completed), fall back to least-recently-used
4. Pick topic (random from available, or LRU on fallback)
5. Retrieve top-k=3 chunks for that topic from Chroma
6. Build prompt (system + retrieved context + JSON output instruction)
7. Call Ollama → parse JSON {anecdote, question}
8. Validate (non-empty, reasonable length)
9. Send email
10. Log to SQLite (topic, chunk_ids, generated text, model)
11. Append run summary to logs/run.log
```

## Generation Prompt (Draft)

```
SYSTEM:
You are an interview prep assistant. Given excerpts from a personal ML
system design crash course, produce ONE concise concept refresher
(3-5 sentences) and ONE thoughtful interview question that probes
understanding of that concept.

Constraints:
- Ground both outputs strictly in the provided excerpts.
- Do not invent company names, statistics, or external facts.
- Refresher should be memorable and tight — no fluff.
- Question should be open-ended (not yes/no).

Output ONLY valid JSON: {"anecdote": "...", "question": "..."}

USER:
Topic: {topic}

Excerpts:
{retrieved_chunks}
```

## Build Order (Milestones)

| Day | Milestone | Verifies |
|-----|-----------|----------|
| 1 | `ingest.py` works; manual REPL retrieval returns relevant chunks | RAG layer |
| 2 | `agent.py` generates valid JSON output from retrieved chunks | Generation layer |
| 3 | `memory.py` + topic rotation working; no repeats within window | Memory layer |
| 4 | `send_email.py` delivers; `run_daily.py` orchestrates end-to-end | Delivery layer |
| 5 | `run_daily.sh` + Task Scheduler firing at 8am | Trigger layer |
| 6 (optional) | Convert to true agentic loop: LLM uses `retrieve(query)` as a tool | Agentic upgrade |

**Each day must end with a working, testable artifact.** Don't build all layers half-finished.

## Configuration

`config.py`:
```python
OLLAMA_BASE_URL = "http://localhost:11434"
GEN_MODEL = "qwen2.5:7b"
EMBED_MODEL = "nomic-embed-text"
CHUNK_SIZE = 500           # tokens, approximate
CHUNK_OVERLAP = 50
TOP_K = 3
RECENCY_DAYS = 14
CHROMA_PATH = "./chroma_db"
HISTORY_DB_PATH = "./history.db"
SOURCE_DOC = "./data/crash_course.md"
LOG_PATH = "./logs/run.log"
```

`.env`:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
EMAIL_TO=your_email@gmail.com
```

## Windows Task Scheduler Setup

**Action:**
- Program: `wsl.exe`
- Arguments: `-d Ubuntu -e bash -lc "cd ~/interview-agent && ./run_daily.sh"`

**Trigger:** Daily at 08:00.

**Settings:**
- "Run only when user is logged on" (acceptable for personal dev machine)
- "Stop the task if it runs longer than 10 minutes"

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
} >> logs/run.log 2>&1
```

## Open Questions (revisit after Day 1)

- How many distinct topics does the doc actually have? Determines optimal `RECENCY_DAYS`.
- Is markdown heading depth consistent enough to use as topic boundaries, or do we need a different chunking strategy?
- After a few days of real outputs, do refreshers feel grounded enough? If hallucination shows up, tighten the prompt or lower temperature.

## Out of Scope (Explicitly Deferred)

- Multiple source documents
- Web UI
- Difficulty calibration / spaced repetition (could be a v2 — much more interesting once basic flow works)
- Reply-to-the-email-with-your-answer feedback loop
- Multi-step agent reasoning
