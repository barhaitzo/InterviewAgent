"""
Parses the source document into chunks, embeds via Ollama, and loads into ChromaDB.

Run once to populate the vector store, or re-run after doc changes:
  python pipeline/ingest.py
"""
import hashlib
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
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


class Ingester:
    def __init__(
        self,
        source_path: Path = config.SOURCE_DOC,
        chroma_path: Path = config.CHROMA_PATH,
        collection_name: str = config.COLLECTION_NAME,
        embed_model: str = config.EMBED_MODEL,
        chunk_size: int = config.CHUNK_SIZE,
        chunk_overlap: int = config.CHUNK_OVERLAP,
        batch_size: int = 20,
        embed_workers: int = 4,
    ) -> None:
        self.source_path = source_path
        self.collection_name = collection_name
        self.embed_model = embed_model
        self.max_chars = chunk_size * 4
        self.overlap_chars = chunk_overlap * 4
        self.batch_size = batch_size
        self.embed_workers = embed_workers
        self._client = chromadb.PersistentClient(path=str(chroma_path))

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _chunk_id(self, heading_path: str, chunk_index: int) -> str:
        key = f"{heading_path}::{chunk_index}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _split_long_text(self, text: str) -> list[str]:
        """Split text into overlapping char-bounded chunks, breaking on newlines where possible."""
        if len(text) <= self.max_chars:
            return [text] if text else []

        parts: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.max_chars, len(text))
            if end < len(text):
                boundary = text.rfind("\n", start, end)
                if boundary > start:
                    end = boundary
            parts.append(text[start:end].strip())
            next_start = end - self.overlap_chars
            # Guard: ensure we always advance to avoid infinite loops when a
            # newline sits very close to `start`.
            start = next_start if next_start > start else end

        return [p for p in parts if p]

    def parse_chunks(self) -> list[dict]:
        """
        Walk the markdown line-by-line, tracking heading context.
        On each heading transition, flush accumulated lines as chunk(s).

        topic        = ## heading (or # heading when no ## is set)
        heading_path = "H1 > H2 > H3" with empty levels omitted
        """
        content = self.source_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        chunks: list[dict] = []
        h1 = h2 = h3 = ""
        section_lines: list[str] = []

        def flush(h1: str, h2: str, h3: str, pending: list[str]) -> None:
            text = "\n".join(pending).strip()
            if not text:
                return
            heading_path = " > ".join(p for p in [h1, h2, h3] if p)
            topic = h2 or h1
            for i, part in enumerate(self._split_long_text(text)):
                chunks.append({
                    "id": self._chunk_id(heading_path, i),
                    "document": part,
                    "metadata": {
                        "topic": topic,
                        "heading_path": heading_path,
                        "chunk_index": i,
                        "source": self.source_path.name,
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

    # ------------------------------------------------------------------
    # Embedding + loading
    # ------------------------------------------------------------------

    def _embed_one(self, chunk: dict) -> list[float]:
        return ollama.embeddings(model=self.embed_model, prompt=chunk["document"])["embedding"]

    def _init_collection(self):
        try:
            self._client.delete_collection(self.collection_name)
            logger.info("Dropped existing '%s' collection.", self.collection_name)
        except Exception:
            pass
        return self._client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def embed_and_load(self, chunks: list[dict], collection) -> None:
        """Embed in parallel within each batch, write batch to Chroma, repeat."""
        total = len(chunks)
        logger.info(
            "Embedding + loading %d chunks (batch=%d, workers=%d)...",
            total, self.batch_size, self.embed_workers,
        )
        for batch_start in range(0, total, self.batch_size):
            batch = chunks[batch_start : batch_start + self.batch_size]
            with ThreadPoolExecutor(max_workers=self.embed_workers) as pool:
                embeddings = list(pool.map(self._embed_one, batch))
            collection.add(
                ids=[c["id"] for c in batch],
                documents=[c["document"] for c in batch],
                embeddings=embeddings,
                metadatas=[c["metadata"] for c in batch],
            )
            logger.info("  %d / %d chunks ingested", min(batch_start + self.batch_size, total), total)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        if not self.source_path.exists():
            raise FileNotFoundError(f"Source document not found: {self.source_path}")

        logger.info("Parsing %s...", self.source_path)
        chunks = self.parse_chunks()
        logger.info("Parsed %d total chunks.", len(chunks))

        topic_counts: dict[str, int] = {}
        for c in chunks:
            t = c["metadata"]["topic"]
            topic_counts[t] = topic_counts.get(t, 0) + 1
        logger.info("Distinct topics: %d", len(topic_counts))
        for topic, count in sorted(topic_counts.items()):
            logger.info("  [%2d chunks] %s", count, topic)

        collection = self._init_collection()
        self.embed_and_load(chunks, collection)

        # Smoke-test: round-trip one retrieval
        collection = self._client.get_collection(self.collection_name)
        logger.info("Collection size: %d documents", collection.count())

        sample_topic = next(iter(topic_counts))
        test_emb = ollama.embeddings(model=self.embed_model, prompt=sample_topic)["embedding"]
        results = collection.query(
            query_embeddings=[test_emb],
            n_results=1,
            where={"topic": sample_topic},
        )
        logger.info("Smoke-test retrieval for topic '%s':", sample_topic)
        logger.info("  %.200s", results["documents"][0][0])


if __name__ == "__main__":
    Ingester().run()
