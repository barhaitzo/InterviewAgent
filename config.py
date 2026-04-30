from pathlib import Path

OLLAMA_BASE_URL = "http://localhost:11434"
GEN_MODEL = "qwen2.5:7b"
EMBED_MODEL = "nomic-embed-text"

# Generation provider: "anthropic", "openai", or "ollama"
# Falls back to Ollama automatically if the API key is missing or invalid.
GEN_PROVIDER = "ollama"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
OPENAI_MODEL = "gpt-4o"

CHUNK_SIZE = 500        # approximate tokens per chunk
CHUNK_OVERLAP = 50      # approximate token overlap between chunks
TOP_K = 3               # chunks retrieved per topic

RECENCY_DAYS = 14       # topics used within this window are skipped

COLLECTION_NAME = "ml_system_design"  # change this when swapping interview topics

CHROMA_PATH = Path("./storage/chroma_db")
HISTORY_DB_PATH = Path("./storage/history.db")
SOURCE_DOC = Path("./data/ml_system_design_crash_course.md")
LOG_PATH = Path("./logs/run.log")
