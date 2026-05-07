"""SQLite-backed topic history. Tracks what was sent and when, drives rotation logic."""
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

logger = logging.getLogger(__name__)


class Memory:
    def __init__(
        self,
        db_path: Path = config.HISTORY_DB_PATH,
        recency_days: int = config.RECENCY_DAYS,
    ) -> None:
        self.db_path = db_path
        self.recency_days = recency_days
        self._init_db()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_anecdotes (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT NOT NULL,
                    topic           TEXT NOT NULL,
                    chunk_ids_used  TEXT NOT NULL,
                    anecdote_text   TEXT NOT NULL,
                    question_text   TEXT NOT NULL,
                    model_used      TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_topic_timestamp
                ON sent_anecdotes (topic, timestamp)
            """)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_recent_topics(self) -> list[str]:
        """Return distinct topics sent within the recency window."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT topic FROM sent_anecdotes "
                "WHERE timestamp >= datetime('now', ?)",
                (f"-{self.recency_days} days",),
            ).fetchall()
        return [row["topic"] for row in rows]

    def get_last_topic(self) -> str | None:
        """Return the most recently sent topic, or None if no history."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT topic FROM sent_anecdotes ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        return row["topic"] if row else None

    def get_lru_topic(self, all_topics: list[str]) -> str:
        """Return the topic with the oldest last-sent timestamp (never-sent topics first)."""
        if not all_topics:
            raise ValueError("all_topics must not be empty.")
        with self._connect() as conn:
            placeholders = ",".join("?" * len(all_topics))
            rows = conn.execute(
                f"SELECT topic, MAX(timestamp) AS last_sent FROM sent_anecdotes "
                f"WHERE topic IN ({placeholders}) GROUP BY topic",
                all_topics,
            ).fetchall()
        sent = {row["topic"]: row["last_sent"] for row in rows}
        return min(all_topics, key=lambda t: sent.get(t) or "")

    def log_run(
        self,
        topic: str,
        chunk_ids: list[str],
        anecdote: str,
        key_takeaway: str,
        model: str = config.GEN_MODEL,
    ) -> None:
        """Insert a row recording today's send."""
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO sent_anecdotes "
                    "(timestamp, topic, chunk_ids_used, anecdote_text, question_text, model_used) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        topic,
                        json.dumps(chunk_ids),
                        anecdote,
                        key_takeaway,
                        model,
                    ),
                )
        except sqlite3.Error as exc:
            logger.error(
                "Failed to log run to history DB (%s) — this topic may repeat next cycle.", exc
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    mem = Memory()
    mem.log_run(
        topic="__smoke_test__",
        chunk_ids=["abc", "def"],
        anecdote="Test anecdote.",
        key_takeaway="Test key takeaway.",
    )
    recent = mem.get_recent_topics()
    logger.info("Recent topics (last %d days): %s", mem.recency_days, recent)
    logger.info("Smoke test passed — history.db written.")
