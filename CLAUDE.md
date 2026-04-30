# CLAUDE.md

Working notes for Claude Code. Read `PROJECT_SPEC.md` first for full context — this file is the operating layer on top of it.

## Project at a glance

Local always-on agentic system. Daily email with ML system design concept refresher + interview question, grounded via RAG over a personal crash course markdown doc. Runs in WSL Ubuntu, triggered by Windows Task Scheduler. Fully local (Ollama). No paid APIs.

## Environment

- **OS:** WSL2 Ubuntu (developing inside Linux filesystem at `~/interview-agent/`, NOT under `/mnt/c/`)
- **Python:** 3.11+, virtualenv at `.venv/`
- **Ollama:** runs on Windows host, reachable from WSL at `http://localhost:11434`
- **Models required (user pulls these on Windows):**
  - `qwen2.5:7b` — generation
  - `nomic-embed-text` — embeddings

Verify Ollama reachable from WSL before any LLM work:
```bash
curl http://localhost:11434/api/tags
```

## Conventions

- All paths in code use `pathlib.Path`, relative to project root.
- All config lives in `config.py`. Never hardcode model names, paths, or thresholds in other modules.
- Secrets in `.env`, loaded via `python-dotenv`. `.env` is gitignored.
- Logging: every module uses `logging` (not `print`). `run_daily.sh` redirects stdout/stderr to `logs/run.log`.
- LLM JSON outputs: always validate with a Pydantic model before use. Retry once on parse failure with a "your previous output was invalid JSON" follow-up; fail loudly on second failure.
- SQLite: use `sqlite3` stdlib with `Row` factory; wrap connections in context managers.
- Chroma: use the `PersistentClient`, not in-memory.

## Build order (one milestone at a time — don't skip ahead)

1. `ingest.py` — markdown → chunks → Chroma. Verify with a REPL retrieval.
2. `agent.py` — retrieve + generate + parse JSON. Verify output quality manually.
3. `memory.py` — SQLite history; integrate topic rotation into agent.
4. `send_email.py` + `run_daily.py` — full local end-to-end via `python run_daily.py`.
5. `run_daily.sh` + Windows Task Scheduler — automated trigger.
6. (Optional, later) Convert to true agentic loop with tool-calling.

Each milestone ends with something runnable and testable. Confirm with the user before moving to the next.

## Things to actively avoid

- Don't add frameworks (LangChain, LlamaIndex, smolagents, etc.) for v1. Hand-roll. The user wants to *understand* what an agent is.
- Don't add features outside the spec without asking — especially: web search, multiple docs, UI, difficulty levels, spaced repetition.
- Don't put project files under `/mnt/c/...` — WSL Linux filesystem only.
- Don't install Ollama inside WSL — use the Windows host installation.
- Don't write to `chroma_db/` or `history.db` in tests; use temp dirs.
- Don't print secrets in logs.

## Markdown chunking notes

The source doc is markdown with `#`/`##`/`###` headings. Chunk by heading sections, then split long sections by token count (~500 with ~50 overlap). Each chunk's metadata must include the full heading path (e.g. `"Sharding > Consistent Hashing"`) and a `topic` field (top-level or second-level heading — decide after looking at the doc).

Before implementing chunking: read the actual doc and report back its heading structure so we can pick the right `topic` granularity.

## Prompt design

System prompt enforces:
- Grounding strictly in retrieved excerpts
- No invented companies, stats, or external facts
- 3–5 sentence refresher, one open-ended question
- JSON-only output: `{"anecdote": "...", "question": "..."}`

Use low temperature (0.3–0.5) for grounding stability. Keep the prompt short — Qwen 2.5 7B follows clean instructions well; don't over-engineer.

## Memory logic

Before generation:
```
all_topics = distinct topics in Chroma
recent_topics = topics in history.db within RECENCY_DAYS
available = all_topics - recent_topics
if available is empty: pick least-recently-used topic instead
pick = random.choice(available)
```

After generation, log to SQLite. The chunk IDs used go in as a JSON array.

## Testing approach

No formal test suite required for v1, but each module should have a `if __name__ == "__main__":` smoke test:
- `ingest.py` — print number of chunks ingested and a sample
- `agent.py` — generate one anecdote/question and print to stdout
- `memory.py` — insert dummy row, query last 14 days, print results
- `send_email.py` — send a test email to self with subject "[TEST]"
- `run_daily.py` — full pipeline, but with `--dry-run` flag that skips actually sending

## Current status

[ ] Day 1: Ingestion + retrieval
[ ] Day 2: Generation
[ ] Day 3: Memory + rotation
[ ] Day 4: Email + orchestration
[ ] Day 5: Task Scheduler integration
[ ] Day 6 (optional): True agentic loop with tool-calling

Update this checklist as milestones complete.

## When in doubt

Ask the user before:
- Adding any new dependency beyond `chromadb`, `ollama`, `python-dotenv`, `pydantic`
- Changing the file layout in `PROJECT_SPEC.md`
- Modifying the generation prompt structure
- Increasing scope beyond the current milestone
