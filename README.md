# Interview Agent

A local, always-on agentic system that delivers one **concept refresher** + one **interview question** to your inbox every morning — grounded in your own study material, zero paid APIs.

Built as a learning project to understand RAG pipelines and agentic systems from the ground up, without frameworks.

---

## How it works

```
Windows Task Scheduler (10am & 14pm)
        ↓
   run_daily.sh  (activates venv)
        ↓
   run_daily.py
        ↓ picks an unseen topic from SQLite history
   pipeline/agent.py
        ↓ embeds topic → queries ChromaDB → retrieves top-3 chunks
   Ollama (qwen2.5:7b)
        ↓ generates JSON {anecdote, question}
   pipeline/email_sender.py
        ↓ Gmail SMTP
   Your inbox
```

- **RAG layer:** ChromaDB (cosine similarity, persistent) + `nomic-embed-text` embeddings
- **Generation:** `qwen2.5:7b` via Ollama — runs fully locally on Windows host
- **Memory:** SQLite tracks sent topics; avoids repeats within a 14-day window
- **Delivery:** Gmail SMTP with App Password auth

---

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| LLM runtime | Ollama (Windows host, WSL-accessible at `localhost:11434`) |
| Generation model | `qwen2.5:7b` |
| Embedding model | `nomic-embed-text` |
| Vector store | ChromaDB (file-based) |
| History store | SQLite (`stdlib`) |
| Email | `smtplib` + Gmail App Password |
| Scheduler | Windows Task Scheduler → WSL |

---

## Project structure

```
interview_agent/
  config.py             # all tunable settings
  run_daily.py          # orchestrator (--dry-run flag available)
  run_daily.sh          # bash entry point for Task Scheduler

  pipeline/
    ingest.py           # markdown → chunks → ChromaDB
    agent.py            # retrieve + generate + parse
    memory.py           # SQLite read/write, topic rotation
    email_sender.py     # SMTP delivery

  data/
    crash_course.md     # source document (swap to change interview topic)

  storage/              # auto-created at runtime, gitignored
    chroma_db/          # vector store
    history.db          # topic history

  docs/
    PROJECT_SPEC.md     # full architecture and design decisions
```

---

## Setup

### 1. Prerequisites

- WSL2 Ubuntu
- Python 3.11+
- [Ollama](https://ollama.com) installed on Windows with these models pulled:

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

### 2. Clone and install

```bash
git clone https://github.com/barhaitzo/InterviewAgent.git
cd InterviewAgent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure secrets

```bash
cp .env.example .env
```

Edit `.env` with your Gmail credentials. You'll need a [Gmail App Password](https://myaccount.google.com/apppasswords) (requires 2FA).

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
EMAIL_TO=your@gmail.com
```

### 4. Ingest your source document

Place your study material in `data/crash_course.md` (markdown with `#`/`##`/`###` headings), then run **from a native WSL terminal** (not through an IDE terminal — this step is memory-intensive):

```bash
source .venv/bin/activate
python pipeline/ingest.py
```

This parses the document, generates embeddings, and loads everything into ChromaDB. Run once, or re-run whenever the source doc changes.

### 5. Test the full pipeline

```bash
python run_daily.py --dry-run
```

Skips sending email and prints the generated anecdote + question to stdout instead.

### 6. Send a test email

```bash
python pipeline/email_sender.py
```

### 7. Automate with Windows Task Scheduler

Open **Task Scheduler** on Windows → **Create Basic Task** → name it `Interview Agent`.

**Trigger tab** — add two daily triggers:
- `10:00` — click New → Daily → 10:00
- `14:00` — click New → Daily → 14:00

**Action tab:**
- Action: `Start a program`
- Program: `wsl.exe`
- Arguments: `-d Ubuntu -e bash -lc "cd /home/<your-username>/interview_agent && ./run_daily.sh"`

> Use the full Linux path (e.g. `/home/<your-username>/interview_agent`) — Task Scheduler does not expand `~`.

**Settings tab:**
- Stop the task if it runs longer than: `10 minutes`
- If the task is already running: `Do not start a new instance`

**Test it:** Right-click the task → **Run**, then check the log:

```bash
tail ~/interview_agent/logs/run.log
```

---

## Changing the interview topic

1. Replace `data/crash_course.md` with your new source document
2. Update `COLLECTION_NAME` in `config.py`
3. Re-run `python pipeline/ingest.py`

Everything else stays the same.

---

## Configuration

All tunable settings live in `config.py`:

| Variable | Default | Description |
|---|---|---|
| `GEN_MODEL` | `qwen2.5:7b` | Ollama generation model |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `CHUNK_SIZE` | `500` | Approximate tokens per chunk |
| `TOP_K` | `3` | Chunks retrieved per topic |
| `RECENCY_DAYS` | `14` | Topic repeat window (days) |
| `COLLECTION_NAME` | `ml_system_design` | ChromaDB collection name |
