import pytest
from unittest.mock import MagicMock, patch

import config
from run_daily import pick_topic


def _agent(topics: list[str]) -> MagicMock:
    agent = MagicMock()
    agent.get_all_topics.return_value = topics
    return agent


def _memory(recent: list[str], lru: str | None = None, last: str | None = None) -> MagicMock:
    memory = MagicMock()
    memory.get_recent_topics.return_value = recent
    memory.get_last_topic.return_value = last
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


class TestPickTopicSequential:
    def _pick(self, topics, last):
        with patch.object(config, "SEQUENTIAL_LEARNING", True):
            return pick_topic(_agent(topics), _memory([], last=last))

    def test_no_history_returns_first_topic(self):
        assert self._pick(["A", "B", "C"], last=None) == "A"

    def test_advances_past_last_topic(self):
        assert self._pick(["A", "B", "C"], last="A") == "B"

    def test_advances_past_middle_topic(self):
        assert self._pick(["A", "B", "C"], last="B") == "C"

    def test_wraps_around_at_end(self):
        assert self._pick(["A", "B", "C"], last="C") == "A"

    def test_last_topic_not_in_collection_starts_from_beginning(self):
        assert self._pick(["A", "B", "C"], last="Z") == "A"

    def test_single_topic_always_returned(self):
        assert self._pick(["A"], last="A") == "A"

    def test_random_mode_not_used(self):
        with patch.object(config, "SEQUENTIAL_LEARNING", True):
            memory = _memory(["A", "B", "C"], last="A")
            pick_topic(_agent(["A", "B", "C"]), memory)
            memory.get_recent_topics.assert_not_called()
            memory.get_lru_topic.assert_not_called()
