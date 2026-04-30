"""
SQLite-backed topic history. Tracks what was sent and when, drives rotation logic.

Run: python memory.py
"""
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

logger = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.HISTORY_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every run."""
    with _connect() as conn:
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


def get_recent_topics(days: int = config.RECENCY_DAYS) -> list[str]:
    """Return distinct topics sent within the last `days` days."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT topic FROM sent_anecdotes "
            "WHERE timestamp >= datetime('now', ?)",
            (f"-{days} days",),
        ).fetchall()
    return [row["topic"] for row in rows]


def get_least_recently_used_topic(all_topics: list[str]) -> str:
    """
    Return the topic with the oldest last-sent timestamp.
    Topics never sent sort before any sent topic (treated as infinitely overdue).
    """
    with _connect() as conn:
        placeholders = ",".join("?" * len(all_topics))
        rows = conn.execute(
            f"SELECT topic, MAX(timestamp) AS last_sent FROM sent_anecdotes "
            f"WHERE topic IN ({placeholders}) GROUP BY topic",
            all_topics,
        ).fetchall()

    sent = {row["topic"]: row["last_sent"] for row in rows}
    # Topics with no history get "" which sorts before any ISO timestamp
    return min(all_topics, key=lambda t: sent.get(t) or "")


def log_run(
    topic: str,
    chunk_ids: list[str],
    anecdote: str,
    question: str,
    model: str = config.GEN_MODEL,
) -> None:
    """Insert a row recording today's send."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sent_anecdotes "
            "(timestamp, topic, chunk_ids_used, anecdote_text, question_text, model_used) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                topic,
                json.dumps(chunk_ids),
                anecdote,
                question,
                model,
            ),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    log_run(
        topic="__smoke_test__",
        chunk_ids=["abc", "def"],
        anecdote="Test anecdote.",
        question="Test question?",
    )
    recent = get_recent_topics(days=14)
    logger.info("Recent topics (last 14 days): %s", recent)
    logger.info("Smoke test passed — history.db written.")
