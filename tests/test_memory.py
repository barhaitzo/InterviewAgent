import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from pipeline.memory import Memory


@pytest.fixture
def memory(tmp_db_path: Path) -> Memory:
    return Memory(db_path=tmp_db_path, recency_days=14)


def _insert(memory: Memory, topic: str, days_ago: float = 0) -> None:
    """Insert a row with a timestamp offset by days_ago from now."""
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    with memory._connect() as conn:
        conn.execute(
            "INSERT INTO sent_anecdotes "
            "(timestamp, topic, chunk_ids_used, anecdote_text, question_text, model_used) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, topic, json.dumps(["c1"]), "anecdote", "question", "model"),
        )


# ---------------------------------------------------------------------------
# get_recent_topics
# ---------------------------------------------------------------------------

class TestGetRecentTopics:
    def test_empty_db_returns_empty(self, memory):
        assert memory.get_recent_topics() == []

    def test_recent_topic_is_included(self, memory):
        _insert(memory, "Feature Stores", days_ago=1)
        assert "Feature Stores" in memory.get_recent_topics()

    def test_topic_older_than_window_excluded(self, memory):
        _insert(memory, "Feature Stores", days_ago=15)
        assert "Feature Stores" not in memory.get_recent_topics()

    def test_topic_at_edge_of_window_included(self, memory):
        _insert(memory, "Feature Stores", days_ago=13)
        assert "Feature Stores" in memory.get_recent_topics()

    def test_same_topic_sent_twice_deduplicated(self, memory):
        _insert(memory, "Feature Stores", days_ago=1)
        _insert(memory, "Feature Stores", days_ago=2)
        assert memory.get_recent_topics().count("Feature Stores") == 1

    def test_only_recent_returned_when_mixed(self, memory):
        _insert(memory, "Recent Topic", days_ago=5)
        _insert(memory, "Old Topic", days_ago=20)
        recent = memory.get_recent_topics()
        assert "Recent Topic" in recent
        assert "Old Topic" not in recent


# ---------------------------------------------------------------------------
# get_lru_topic
# ---------------------------------------------------------------------------

class TestGetLruTopic:
    def test_never_sent_topic_beats_sent_topic(self, memory):
        _insert(memory, "Sent", days_ago=1)
        assert memory.get_lru_topic(["Sent", "Never"]) == "Never"

    def test_oldest_sent_topic_returned(self, memory):
        _insert(memory, "A", days_ago=10)
        _insert(memory, "B", days_ago=2)
        assert memory.get_lru_topic(["A", "B"]) == "A"

    def test_single_topic_list(self, memory):
        assert memory.get_lru_topic(["Only"]) == "Only"

    def test_all_never_sent_returns_one_of_them(self, memory):
        result = memory.get_lru_topic(["X", "Y", "Z"])
        assert result in ["X", "Y", "Z"]

    def test_multiple_never_sent_topics_stable_order(self, memory):
        # min() on "" for all never-sent topics — result depends on list order, just check it's valid
        result = memory.get_lru_topic(["A", "B"])
        assert result in ["A", "B"]


# ---------------------------------------------------------------------------
# log_run
# ---------------------------------------------------------------------------

class TestLogRun:
    def test_row_inserted(self, memory):
        memory.log_run("Feature Stores", ["a", "b"], "anecdote text", "question text?")
        with memory._connect() as conn:
            rows = conn.execute("SELECT * FROM sent_anecdotes").fetchall()
        assert len(rows) == 1

    def test_correct_topic_stored(self, memory):
        memory.log_run("Feature Stores", ["a"], "anecdote", "question")
        with memory._connect() as conn:
            row = conn.execute("SELECT topic FROM sent_anecdotes").fetchone()
        assert row["topic"] == "Feature Stores"

    def test_chunk_ids_stored_as_json_array(self, memory):
        memory.log_run("T", ["x", "y", "z"], "a", "q")
        with memory._connect() as conn:
            row = conn.execute("SELECT chunk_ids_used FROM sent_anecdotes").fetchone()
        assert json.loads(row["chunk_ids_used"]) == ["x", "y", "z"]

    def test_multiple_runs_all_stored(self, memory):
        memory.log_run("A", ["c1"], "a1", "q1")
        memory.log_run("B", ["c2"], "a2", "q2")
        with memory._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM sent_anecdotes").fetchone()[0]
        assert count == 2

    def test_logged_topic_appears_in_recent(self, memory):
        memory.log_run("New Topic", ["c1"], "a", "q")
        assert "New Topic" in memory.get_recent_topics()
