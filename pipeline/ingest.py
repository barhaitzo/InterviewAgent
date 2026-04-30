"""
Parses crash_course.md into chunks, embeds via Ollama, and loads into ChromaDB.

Run once to populate the vector store, or re-run to refresh after doc changes.
Usage: python ingest.py
"""
import hashlib
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["CHROMA_TELEMETRY"] = "false"

import chromadb
import ollama

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _chunk_id(heading_path: str, chunk_index: int) -> str:
    key = f"{heading_path}::{chunk_index}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _split_long_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Split text into overlapping char-bounded chunks, breaking on newlines where possible."""
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary > start:
                end = boundary
        parts.append(text[start:end].strip())
        next_start = end - overlap_chars
        # Guard: if overlap would send us backwards, skip it and advance to end.
        # Without this, a newline close to `start` causes rfind to find the same
        # boundary on every iteration → infinite loop.
        start = next_start if next_start > start else end

    return [p for p in parts if p]


def parse_chunks(source_path: Path) -> list[dict]:
    """
    Walk the markdown line-by-line, tracking heading context.
    On each heading transition, flush accumulated lines as chunk(s).

    topic   = ## heading (or # heading when no ## has been seen)
    heading_path = "h1 > h2 > h3" with empty levels omitted
    """
    content = source_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # 1 token ≈ 4 chars (rough but dependency-free)
    max_chars = config.CHUNK_SIZE * 4
    overlap_chars = config.CHUNK_OVERLAP * 4

    chunks: list[dict] = []
    h1 = h2 = h3 = ""
    section_lines: list[str] = []

    def flush(h1: str, h2: str, h3: str, pending: list[str]) -> None:
        text = "\n".join(pending).strip()
        if not text:
            return
        heading_path = " > ".join(p for p in [h1, h2, h3] if p)
        topic = h2 or h1
        for i, part in enumerate(_split_long_text(text, max_chars, overlap_chars)):
            chunks.append({
                "id": _chunk_id(heading_path, i),
                "document": part,
                "metadata": {
                    "topic": topic,
                    "heading_path": heading_path,
                    "chunk_index": i,
                    "source": source_path.name,
                },
            })

    for line in lines:
        if line.startswith("### "):
            flush(h1, h2, h3, section_lines)
            h3 = line[4:].strip()
            section_lines = []
        elif line.startswith("## "):
            flush(h1, h2, h3, section_lines)
            h2 = line[3:].strip()
            h3 = ""
            section_lines = []
        elif line.startswith("# "):
            flush(h1, h2, h3, section_lines)
            h1 = line[2:].strip()
            h2 = h3 = ""
            section_lines = []
        else:
            section_lines.append(line)

    flush(h1, h2, h3, section_lines)
    return chunks


# ---------------------------------------------------------------------------
# Embed + load (batched to keep peak RAM low)
# ---------------------------------------------------------------------------

_BATCH_SIZE = 20  # embed this many chunks at a time before writing to Chroma


def embed_and_load(chunks: list[dict], collection) -> None:
    """
    Embed chunks in small batches and add each batch to Chroma immediately.
    This avoids holding all embeddings in memory at once.
    """
    total = len(chunks)
    logger.info("Embedding + loading %d chunks (batch=%d)...", total, _BATCH_SIZE)

    for batch_start in range(0, total, _BATCH_SIZE):
        batch = chunks[batch_start : batch_start + _BATCH_SIZE]
        embeddings = [
            ollama.embeddings(model=config.EMBED_MODEL, prompt=c["document"])["embedding"]
            for c in batch
        ]
        collection.add(
            ids=[c["id"] for c in batch],
            documents=[c["document"] for c in batch],
            embeddings=embeddings,
            metadatas=[c["metadata"] for c in batch],
        )
        done = min(batch_start + _BATCH_SIZE, total)
        logger.info("  %d / %d chunks ingested", done, total)


def init_collection():
    client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
    try:
        client.delete_collection(config.COLLECTION_NAME)
        logger.info("Dropped existing '%s' collection.", config.COLLECTION_NAME)
    except Exception:
        pass
    return client.create_collection(
        name=config.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    source = config.SOURCE_DOC
    if not source.exists():
        raise FileNotFoundError(f"Source document not found: {source}")

    logger.info("Parsing %s...", source)
    chunks = parse_chunks(source)
    logger.info("Parsed %d total chunks.", len(chunks))

    # Show topic breakdown so we can validate granularity
    topic_counts: dict[str, int] = {}
    for c in chunks:
        t = c["metadata"]["topic"]
        topic_counts[t] = topic_counts.get(t, 0) + 1
    logger.info("Distinct topics: %d", len(topic_counts))
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[0]):
        logger.info("  [%2d chunks] %s", count, topic)

    collection = init_collection()
    embed_and_load(chunks, collection)

    # Smoke-test: round-trip one retrieval
    client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
    collection = client.get_collection(config.COLLECTION_NAME)
    logger.info("Collection size: %d documents", collection.count())

    sample_topic = next(iter(topic_counts))
    test_emb = ollama.embeddings(model=config.EMBED_MODEL, prompt=sample_topic)["embedding"]
    results = collection.query(
        query_embeddings=[test_emb],
        n_results=1,
        where={"topic": sample_topic},
    )
    logger.info("Smoke-test retrieval for topic '%s':", sample_topic)
    logger.info("  %.200s", results["documents"][0][0])


if __name__ == "__main__":
    main()
