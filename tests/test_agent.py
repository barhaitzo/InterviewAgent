import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
from pipeline.agent import Agent, AgentOutput


@pytest.fixture
def mock_agent(tmp_path: Path) -> Agent:
    """Agent with fully mocked ChromaDB — no real files needed."""
    mock_collection = MagicMock()
    with patch("chromadb.PersistentClient") as mock_client:
        mock_client.return_value.get_collection.return_value = mock_collection
        agent = Agent(chroma_path=tmp_path / "chroma", collection_name="test")
    agent._collection = mock_collection
    return agent


def _chat_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.message.content = content
    return resp


# ---------------------------------------------------------------------------
# _parse_output
# ---------------------------------------------------------------------------

class TestParseOutput:
    VALID = '{"anecdote": "foo bar", "question": "why baz?"}'

    def test_clean_json(self, mock_agent):
        out = mock_agent._parse_output(self.VALID)
        assert out.anecdote == "foo bar"
        assert out.question == "why baz?"

    def test_strips_json_fenced_block(self, mock_agent):
        raw = f"```json\n{self.VALID}\n```"
        assert mock_agent._parse_output(raw).anecdote == "foo bar"

    def test_strips_plain_fenced_block(self, mock_agent):
        raw = f"```\n{self.VALID}\n```"
        assert mock_agent._parse_output(raw).anecdote == "foo bar"

    def test_extracts_json_from_surrounding_prose(self, mock_agent):
        raw = f"Sure! Here you go:\n{self.VALID}\nHope that helps."
        assert mock_agent._parse_output(raw).anecdote == "foo bar"

    def test_returns_agent_output_type(self, mock_agent):
        assert isinstance(mock_agent._parse_output(self.VALID), AgentOutput)

    def test_invalid_json_raises(self, mock_agent):
        with pytest.raises((json.JSONDecodeError, KeyError, ValidationError)):
            mock_agent._parse_output("not json at all")

    def test_missing_question_field_raises(self, mock_agent):
        with pytest.raises((ValidationError, KeyError)):
            mock_agent._parse_output('{"anecdote": "foo"}')

    def test_missing_anecdote_field_raises(self, mock_agent):
        with pytest.raises((ValidationError, KeyError)):
            mock_agent._parse_output('{"question": "q?"}')


# ---------------------------------------------------------------------------
# get_all_topics
# ---------------------------------------------------------------------------

class TestGetAllTopics:
    def test_returns_distinct_topics_in_insertion_order(self, mock_agent):
        mock_agent._collection.get.return_value = {
            "metadatas": [
                {"topic": "A"},
                {"topic": "B"},
                {"topic": "A"},
                {"topic": "C"},
            ]
        }
        assert mock_agent.get_all_topics() == ["A", "B", "C"]

    def test_empty_collection_returns_empty_list(self, mock_agent):
        mock_agent._collection.get.return_value = {"metadatas": []}
        assert mock_agent.get_all_topics() == []

    def test_single_topic_returned_once(self, mock_agent):
        mock_agent._collection.get.return_value = {
            "metadatas": [{"topic": "X"}, {"topic": "X"}]
        }
        assert mock_agent.get_all_topics() == ["X"]


# ---------------------------------------------------------------------------
# retrieve
# ---------------------------------------------------------------------------

class TestRetrieve:
    def test_returns_documents_and_ids(self, mock_agent):
        mock_agent._collection.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "ids": [["id1", "id2"]],
        }
        with patch("ollama.embeddings", return_value={"embedding": [0.1, 0.2]}):
            docs, ids = mock_agent.retrieve("Feature Stores")
        assert docs == ["doc1", "doc2"]
        assert ids == ["id1", "id2"]

    def test_topic_filter_passed_to_chroma(self, mock_agent):
        mock_agent._collection.query.return_value = {
            "documents": [[]], "ids": [[]]
        }
        with patch("ollama.embeddings", return_value={"embedding": [0.1]}):
            mock_agent.retrieve("Feature Stores")
        kwargs = mock_agent._collection.query.call_args[1]
        assert kwargs["where"] == {"topic": "Feature Stores"}

    def test_top_k_passed_to_chroma(self, mock_agent):
        mock_agent._collection.query.return_value = {
            "documents": [[]], "ids": [[]]
        }
        with patch("ollama.embeddings", return_value={"embedding": [0.1]}):
            mock_agent.retrieve("Feature Stores")
        kwargs = mock_agent._collection.query.call_args[1]
        assert kwargs["n_results"] == mock_agent.top_k


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

class TestGenerate:
    VALID_PAYLOAD = '{"anecdote": "concept refresher", "question": "open-ended q?"}'

    def test_returns_agent_output(self, mock_agent):
        with patch("ollama.chat", return_value=_chat_response(self.VALID_PAYLOAD)):
            out = mock_agent.generate("topic", ["chunk1"])
        assert isinstance(out, AgentOutput)
        assert out.anecdote == "concept refresher"

    def test_retries_once_on_bad_json(self, mock_agent):
        good = '{"anecdote": "retry worked", "question": "q?"}'
        responses = [_chat_response("not json"), _chat_response(good)]
        with patch("ollama.chat", side_effect=responses) as mock_chat:
            out = mock_agent.generate("topic", ["chunk1"])
        assert mock_chat.call_count == 2
        assert out.anecdote == "retry worked"

    def test_documents_included_in_user_message(self, mock_agent):
        with patch("ollama.chat", return_value=_chat_response(self.VALID_PAYLOAD)) as mock_chat:
            mock_agent.generate("mytopic", ["important chunk"])
        messages = mock_chat.call_args[1]["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "important chunk" in user_msg["content"]
        assert "mytopic" in user_msg["content"]
