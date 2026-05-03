from pathlib import Path

OLLAMA_BASE_URL = "http://localhost:11434"
GEN_MODEL = "llama3.1:8b"
EMBED_MODEL = "nomic-embed-text"

# Agentic mode: LLM calls retrieve() as a tool instead of receiving pre-fetched chunks.
AGENTIC = True
MAX_TOOL_CALLS = 5  # safety cap on retrieval iterations per run

CHUNK_SIZE = 500        # approximate tokens per chunk
CHUNK_OVERLAP = 50      # approximate token overlap between chunks
TOP_K = 3               # chunks retrieved per topic

RECENCY_DAYS = 14       # topics used within this window are skipped

COLLECTION_NAME = "ml_system_design"  # change this when swapping interview topics

CHROMA_PATH = Path("./storage/chroma_db")
HISTORY_DB_PATH = Path("./storage/history.db")
SOURCE_DOC = Path("./data/ml_system_design_crash_course.md")
LOG_PATH = Path("./logs/run.log")
