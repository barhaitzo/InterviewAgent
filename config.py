from pathlib import Path

OLLAMA_BASE_URL = "http://localhost:11434"
GEN_MODEL = "qwen2.5:7b"
EMBED_MODEL = "nomic-embed-text"

CHUNK_SIZE = 500        # approximate tokens per chunk
CHUNK_OVERLAP = 50      # approximate token overlap between chunks
TOP_K = 3               # chunks retrieved per topic

RECENCY_DAYS = 14       # topics used within this window are skipped

COLLECTION_NAME = "ml_system_design"  # change this when swapping interview topics

CHROMA_PATH = Path("./chroma_db")
HISTORY_DB_PATH = Path("./history.db")
SOURCE_DOC = Path("./data/crash_course.md")
LOG_PATH = Path("./logs/run.log")
