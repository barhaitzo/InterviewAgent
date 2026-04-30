import pytest
from unittest.mock import MagicMock

from run_daily import pick_topic


def _agent(topics: list[str]) -> MagicMock:
    agent = MagicMock()
    agent.get_all_topics.return_value = topics
    return agent


def _memory(recent: list[str], lru: str | None = None) -> MagicMock:
    memory = MagicMock()
    memory.get_recent_topics.return_value = recent
    if lru is not None:
        memory.get_lru_topic.return_value = lru
    return memory


class TestPickTopic:
    def test_picks_from_available_topics(self):
        topic = pick_topic(_agent(["A", "B", "C"]), _memory(["A"]))
        assert topic in ["B", "C"]

    def test_never_returns_recent_topic_when_alternatives_exist(self):
        for _ in range(20):  # randomness — run multiple times
            topic = pick_topic(_agent(["A", "B", "C"]), _memory(["A"]))
            assert topic != "A"

    def test_all_topics_available_when_history_empty(self):
        topic = pick_topic(_agent(["A", "B", "C"]), _memory([]))
        assert topic in ["A", "B", "C"]

    def test_falls_back_to_lru_when_all_recent(self):
        agent = _agent(["A", "B"])
        memory = _memory(["A", "B"], lru="A")
        topic = pick_topic(agent, memory)
        memory.get_lru_topic.assert_called_once_with(["A", "B"])
        assert topic == "A"

    def test_lru_not_called_when_available_topics_exist(self):
        memory = _memory(["A"], lru="A")
        pick_topic(_agent(["A", "B"]), memory)
        memory.get_lru_topic.assert_not_called()

    def test_single_topic_not_recent_is_returned(self):
        assert pick_topic(_agent(["A"]), _memory([])) == "A"

    def test_single_topic_recent_falls_back_to_lru(self):
        memory = _memory(["A"], lru="A")
        assert pick_topic(_agent(["A"]), memory) == "A"
        memory.get_lru_topic.assert_called_once()
