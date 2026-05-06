import re
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
SEQUENTIAL_LEARNING = True  # if True, walk topics in document order instead of random

COURSE_NAME = "AI-assisted backend interview crash course"  # only this needs to change when swapping courses, should be similar to the source doc filename
COLLECTION_NAME = re.sub(r"[^a-z0-9]+", "_", COURSE_NAME.lower()).strip("_")
SOURCE_DOC = Path(f"./data/{COLLECTION_NAME}.md")

CHROMA_PATH = Path("./storage/chroma_db")
HISTORY_DB_PATH = Path("./storage/history.db")
LOG_PATH = Path("./logs/run.log")
