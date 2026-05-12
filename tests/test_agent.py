import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
from pipeline.agent import Agent, AgentOutput


@pytest.fixture
def mock_agent(tmp_path: Path) -> Agent:
    """Agent with fully mocked ChromaDB — no real files needed. Always non-agentic."""
    mock_collection = MagicMock()
    with patch("chromadb.PersistentClient") as mock_client:
        mock_client.return_value.get_collection.return_value = mock_collection
        agent = Agent(chroma_path=tmp_path / "chroma", course_name="test", agentic=False)
    agent._collection = mock_collection
    return agent


def _chat_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.message.content = content
    return resp


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
    VALID_PAYLOAD = '{"anecdote": "concept refresher", "key_takeaway": "the key point"}'

    def test_returns_agent_output(self, mock_agent):
        with patch("ollama.chat", return_value=_chat_response(self.VALID_PAYLOAD)):
            out = mock_agent.generate("topic", ["chunk1"])
        assert isinstance(out, AgentOutput)
        assert out.anecdote == "concept refresher"

    def test_key_takeaway_overridden_from_source(self, mock_agent):
        chunk = "Some content.\nKey takeaway: verbatim takeaway from source."
        with patch("ollama.chat", return_value=_chat_response(self.VALID_PAYLOAD)):
            out = mock_agent.generate("topic", [chunk])
        assert out.key_takeaway == "verbatim takeaway from source."

    def test_key_takeaway_from_model_when_not_in_source(self, mock_agent):
        with patch("ollama.chat", return_value=_chat_response(self.VALID_PAYLOAD)):
            out = mock_agent.generate("topic", ["chunk with no takeaway line"])
        assert out.key_takeaway == "the key point"

    def test_schema_format_passed_to_ollama(self, mock_agent):
        with patch("ollama.chat", return_value=_chat_response(self.VALID_PAYLOAD)) as mock_chat:
            mock_agent.generate("topic", ["chunk1"])
        kwargs = mock_chat.call_args[1]
        assert kwargs["format"] == AgentOutput.model_json_schema()

    def test_documents_included_in_user_message(self, mock_agent):
        with patch("ollama.chat", return_value=_chat_response(self.VALID_PAYLOAD)) as mock_chat:
            mock_agent.generate("mytopic", ["important chunk"])
        messages = mock_chat.call_args[1]["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "important chunk" in user_msg["content"]
        assert "mytopic" in user_msg["content"]


# ---------------------------------------------------------------------------
# run() — mode dispatch
# ---------------------------------------------------------------------------

class TestRun:
    VALID_PAYLOAD = '{"anecdote": "refresher", "key_takeaway": "the key point"}'

    def test_non_agentic_uses_retrieve_and_generate(self, mock_agent, tmp_path):
        mock_agent._collection.query.return_value = {
            "documents": [["doc1"]], "ids": [["id1"]]
        }
        with patch("ollama.embeddings", return_value={"embedding": [0.1]}), \
             patch("ollama.chat", return_value=_chat_response(self.VALID_PAYLOAD)):
            output, chunk_ids = mock_agent.run("Feature Stores")
        assert output.anecdote == "refresher"
        assert chunk_ids == ["id1"]

    def test_agentic_mode_dispatches_to_agentic_run(self, tmp_path):
        mock_collection = MagicMock()
        with patch("chromadb.PersistentClient") as mock_client:
            mock_client.return_value.get_collection.return_value = mock_collection
            agent = Agent(
                chroma_path=tmp_path / "chroma",
                course_name="test",
                agentic=True,
            )
        agent._collection = mock_collection

        expected = (AgentOutput(anecdote="a", key_takeaway="the key point"), ["id1"])
        with patch.object(agent, "_agentic_run", return_value=expected) as mock_ar:
            output, ids = agent.run("Feature Stores")
        mock_ar.assert_called_once_with("Feature Stores")
        assert output.anecdote == "a"

    def test_agentic_run_calls_retrieve_tool(self, tmp_path):
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["chunk text"]], "ids": [["id1"]]
        }
        with patch("chromadb.PersistentClient") as mock_client:
            mock_client.return_value.get_collection.return_value = mock_collection
            agent = Agent(
                chroma_path=tmp_path / "chroma",
                course_name="test",
                agentic=True,
            )
        agent._collection = mock_collection

        # First response: tool call; second: end of tool phase; third: format-enforced output
        tool_call = MagicMock()
        tool_call.function.name = "retrieve"
        tool_call.function.arguments = {"query": "feature store architecture"}

        first_resp = MagicMock()
        first_resp.message.tool_calls = [tool_call]
        first_resp.message.content = ""

        done_resp = MagicMock()
        done_resp.message.tool_calls = None
        done_resp.message.content = "here is what I found"

        format_resp = MagicMock()
        format_resp.message.tool_calls = None
        format_resp.message.content = self.VALID_PAYLOAD

        with patch("ollama.embeddings", return_value={"embedding": [0.1]}), \
             patch("ollama.chat", side_effect=[first_resp, done_resp, format_resp]) as mock_chat:
            output, ids = agent._agentic_run("Feature Stores")

        assert output.anecdote == "refresher"
        assert "id1" in ids
        kwargs = mock_collection.query.call_args[1]
        assert kwargs["where"] == {"topic": "Feature Stores"}
        # Third call must use format enforcement
        third_call_kwargs = mock_chat.call_args_list[2][1]
        assert third_call_kwargs["format"] == AgentOutput.model_json_schema()

    def test_agentic_run_always_uses_format_for_final_output(self, tmp_path):
        mock_collection = MagicMock()
        with patch("chromadb.PersistentClient") as mock_client:
            mock_client.return_value.get_collection.return_value = mock_collection
            agent = Agent(
                chroma_path=tmp_path / "chroma",
                course_name="test",
                agentic=True,
            )
        agent._collection = mock_collection

        # Model immediately signals end of tool phase (no tool calls)
        done_resp = MagicMock()
        done_resp.message.tool_calls = None
        done_resp.message.content = "here is what I found"

        format_resp = MagicMock()
        format_resp.message.tool_calls = None
        format_resp.message.content = self.VALID_PAYLOAD

        with patch("ollama.chat", side_effect=[done_resp, format_resp]) as mock_chat:
            output, _ = agent._agentic_run("Feature Stores")

        assert output.anecdote == "refresher"
        # Second call must always use format enforcement
        second_call_kwargs = mock_chat.call_args_list[1][1]
        assert second_call_kwargs["format"] == AgentOutput.model_json_schema()

    def test_agentic_run_overrides_key_takeaway_from_tool_result(self, tmp_path):
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["Some content.\nKey takeaway: verbatim from source."]],
            "ids": [["id1"]],
        }
        with patch("chromadb.PersistentClient") as mock_client:
            mock_client.return_value.get_collection.return_value = mock_collection
            agent = Agent(chroma_path=tmp_path / "chroma", course_name="test", agentic=True)
        agent._collection = mock_collection

        tool_call = MagicMock()
        tool_call.function.name = "retrieve"
        tool_call.function.arguments = {"query": "indexing"}

        tool_resp = MagicMock()
        tool_resp.message.tool_calls = [tool_call]
        tool_resp.message.content = ""

        done_resp = MagicMock()
        done_resp.message.tool_calls = None
        done_resp.message.content = ""

        format_resp = MagicMock()
        format_resp.message.tool_calls = None
        format_resp.message.content = self.VALID_PAYLOAD  # model produces "the key point"

        with patch("ollama.embeddings", return_value={"embedding": [0.1]}), \
             patch("ollama.chat", side_effect=[tool_resp, done_resp, format_resp]):
            output, _ = agent._agentic_run("Feature Stores")

        # Python override wins over model output
        assert output.key_takeaway == "verbatim from source."
