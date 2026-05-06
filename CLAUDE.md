# CLAUDE.md

Working notes for Claude Code. Read `PROJECT_SPEC.md` first for full context — this file is the operating layer on top of it.

## Project at a glance

Local always-on agentic system. Daily email with a concept refresher + interview question, grounded via RAG over a personal crash course markdown doc. Runs in WSL Ubuntu, triggered by Windows Task Scheduler. Fully local (Ollama). No paid APIs.

## Environment

- **OS:** WSL2 Ubuntu (developing inside Linux filesystem at `~/interview_agent/`, NOT under `/mnt/c/`)
- **Python:** 3.11+, virtualenv at `.venv/`
- **Ollama:** runs on Windows host, reachable from WSL at `http://localhost:11434`
- **Models required (user pulls these on Windows):**
  - `llama3.1:8b` — generation
  - `nomic-embed-text` — embeddings

Verify Ollama reachable from WSL before any LLM work:
```bash
curl http://localhost:11434/api/tags
```

## Conventions

- All paths in code use `pathlib.Path`, relative to project root.
- All config lives in `config.py`. Never hardcode model names, paths, or thresholds in other modules.
- Secrets in `.env`, loaded via `python-dotenv`. `.env` is gitignored.
- Logging: every module uses `logging` (not `print`). `run_daily.sh` pipes stdout/stderr through `tee` to `logs/run.log`.
- LLM JSON outputs: always validate with a Pydantic model before use. Retry once on parse failure with a "your previous output was invalid JSON" follow-up; fail loudly on second failure.
- SQLite: use `sqlite3` stdlib with `Row` factory; wrap connections in context managers.
- Chroma: use the `PersistentClient`, not in-memory.

## Things to actively avoid

- Don't add frameworks (LangChain, LlamaIndex, smolagents, etc.). Hand-roll. The user wants to *understand* what an agent is.
- Don't add features outside the spec without asking — especially: web search, multiple docs, UI, difficulty levels, spaced repetition.
- Don't put project files under `/mnt/c/...` — WSL Linux filesystem only.
- Don't install Ollama inside WSL — use the Windows host installation.
- Don't write to `chroma_db/` or `history.db` in tests; use temp dirs.
- Don't print secrets in logs.

## Changing the course

Only `COURSE_NAME` in `config.py` needs to change. `COLLECTION_NAME` and `SOURCE_DOC` are derived from it automatically. After updating, re-run `python pipeline/ingest.py`.

## Prompt design

System prompt enforces:
- Grounding strictly in retrieved excerpts
- No invented companies, stats, or external facts
- 3–5 sentence refresher, one open-ended question
- JSON-only output: `{"anecdote": "...", "question": "..."}`

The course name is injected at runtime via `self.course_name` on the `Agent` instance. Keep the prompt short — `llama3.1:8b` follows clean instructions well; don't over-engineer.

## Topic rotation logic

**Sequential mode** (`SEQUENTIAL_LEARNING=True`): walk topics in ChromaDB insertion order (= document order), advancing past the last-sent topic, wrapping around at the end.

**Random mode** (`SEQUENTIAL_LEARNING=False`):
```
all_topics = distinct topics in Chroma
recent_topics = topics in history.db within RECENCY_DAYS
available = all_topics - recent_topics
if available is empty: pick least-recently-used topic instead
pick = random.choice(available)
```

After generation, log to SQLite. The chunk IDs used go in as a JSON array.

## When in doubt

Ask the user before:
- Adding any new dependency beyond `chromadb`, `ollama`, `python-dotenv`, `pydantic`
- Changing the file layout in `PROJECT_SPEC.md`
- Modifying the generation prompt structure
- Increasing scope without discussion
