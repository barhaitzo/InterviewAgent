"""Retrieval-augmented generation agent: retrieve chunks, call LLM, parse output."""
import logging
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chromadb
import ollama
from pydantic import BaseModel, ValidationError

import config

logger = logging.getLogger(__name__)


class AgentOutput(BaseModel):
    anecdote: str
    key_takeaway: str


class Agent:

    SYSTEM_PROMPT = (
        "You are an interview prep assistant. Given excerpts from a personal {course} "
        "crash course, produce ONE concept refresher and ONE key takeaway.\n\n"
        "Refresher rules:\n"
        "- Write 4–6 sentences of flowing prose. Do NOT use bullet points or numbered lists.\n"
        "- Include the concrete facts from the excerpts: specific numbers, latency figures, "
        "formulas, thresholds, named strategies, decision rules. Do NOT just describe the topic "
        "at a high level — give content the reader can act on.\n"
        "- Ground strictly in the provided excerpts. Do not invent facts.\n\n"
        "Key takeaway rules:\n"
        "- If the excerpts contain a line starting with '**Key takeaway:**', "
        "extract it verbatim (without the prefix).\n"
        "- Otherwise write one tight sentence naming the single most actionable thing to remember.\n\n"
        "Return your answer as a JSON object with keys 'anecdote' and 'key_takeaway'."
    )

    AGENTIC_SYSTEM_PROMPT = (
        "You are an interview prep assistant with access to a retrieve tool that searches a "
        "personal {course} crash course.\n\n"
        "Given a topic, use retrieve() to gather relevant excerpts, then produce ONE concept "
        "refresher and ONE key takeaway.\n\n"
        "Instructions:\n"
        "- Call retrieve 1–3 times to gather what you need.\n"
        "- Refresher: write 4–6 sentences of flowing prose. Do NOT use bullet points or numbered "
        "lists. Include the concrete facts: specific numbers, latency figures, formulas, "
        "thresholds, named strategies, decision rules. Do NOT just describe the topic — give "
        "content the reader can act on. Ground strictly in retrieved content.\n"
        "- Key takeaway: if retrieved content contains a line starting with '**Key takeaway:**', "
        "extract it verbatim (without the prefix). Otherwise write one tight actionable sentence.\n"
        "- Return your answer as a JSON object with keys 'anecdote' and 'key_takeaway'."
    )

    RETRIEVE_TOOL = {
        "type": "function",
        "function": {
            "name": "retrieve",
            "description": (
                "Search the study material for relevant excerpts. "
                "Use a focused query to find content about a specific aspect of the topic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A specific search query to find relevant study material.",
                    }
                },
                "required": ["query"],
            },
        },
    }

    def __init__(
        self,
        chroma_path: Path = config.CHROMA_PATH,
        course_name: str = config.COURSE_NAME,
        embed_model: str = config.EMBED_MODEL,
        gen_model: str = config.GEN_MODEL,
        top_k: int = config.TOP_K,
        agentic: bool = config.AGENTIC,
        max_tool_calls: int = config.MAX_TOOL_CALLS,
    ) -> None:
        self.course_name = course_name
        self.embed_model = embed_model
        self.gen_model = gen_model
        self.top_k = top_k
        self.agentic = agentic
        self.max_tool_calls = max_tool_calls
        self._client = chromadb.PersistentClient(path=str(chroma_path))
        collection_name = course_name.lower().replace("-", "_").replace(" ", "_")
        try:
            self._collection = self._client.get_collection(collection_name)
        except Exception as exc:
            raise RuntimeError(
                f"ChromaDB collection '{collection_name}' not found. "
                "Run 'python pipeline/ingest.py' first."
            ) from exc

    def _heartbeat(self, stop: threading.Event, interval: int = 15) -> None:
        elapsed = 0
        while not stop.wait(interval):
            elapsed += interval
            logger.info("  ... LLM still generating (%ds elapsed)", elapsed)

    # ------------------------------------------------------------------
    # Internal — tool execution
    # ------------------------------------------------------------------

    def _retrieve_for_tool(self, query: str, topic: str) -> tuple[str, list[str]]:
        """Execute a retrieve tool call, scoped to the selected topic."""
        try:
            resp = ollama.embeddings(model=self.embed_model, prompt=query)
        except Exception as exc:
            raise RuntimeError(
                f"Ollama embedding failed — is Ollama running at {config.OLLAMA_BASE_URL}? ({exc})"
            ) from exc
        results = self._collection.query(
            query_embeddings=[resp["embedding"]],
            n_results=self.top_k,
            where={"topic": topic},
        )
        docs = results["documents"][0]
        ids = results["ids"][0]
        formatted = "\n\n---\n\n".join(
            f"[{cid}]\n{doc}" for cid, doc in zip(ids, docs)
        )
        return formatted, ids

    # ------------------------------------------------------------------
    # Internal — agentic loop
    # ------------------------------------------------------------------

    def _agentic_run(self, topic: str) -> tuple[AgentOutput, list[str]]:
        messages: list[dict] = [
            {"role": "system", "content": self.AGENTIC_SYSTEM_PROMPT.format(course=self.course_name)},
            {"role": "user", "content": f"Topic: {topic}"},
        ]
        all_chunk_ids: list[str] = []
        retrieved_contexts: list[str] = []

        for _ in range(self.max_tool_calls):
            try:
                resp = ollama.chat(
                    model=self.gen_model,
                    messages=messages,
                    tools=[self.RETRIEVE_TOOL],
                    options={"temperature": 0.4, "num_predict": 600},
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Ollama agentic call failed — is Ollama running at {config.OLLAMA_BASE_URL}? ({exc})"
                ) from exc

            if not resp.message.tool_calls:
                try:
                    return AgentOutput.model_validate_json(resp.message.content), all_chunk_ids
                except ValidationError:
                    # Output wasn't valid — re-ask with schema enforcement
                    logger.warning("Agentic output failed validation — retrying with format constraint.")
                    messages.append({"role": "assistant", "content": resp.message.content or ""})
                    messages.append({"role": "user", "content": "Now produce the output as structured JSON."})
                    final = ollama.chat(
                        model=self.gen_model,
                        messages=messages,
                        format=AgentOutput.model_json_schema(),
                        options={"temperature": 0.2, "num_predict": 600},
                    )
                    return AgentOutput.model_validate_json(final.message.content), all_chunk_ids

            messages.append({
                "role": "assistant",
                "content": resp.message.content or "",
                "tool_calls": [
                    {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in resp.message.tool_calls
                ],
            })
            for tc in resp.message.tool_calls:
                query = tc.function.arguments.get("query", "")
                logger.info("  [tool] retrieve(%r)", query)
                result, ids = self._retrieve_for_tool(query, topic)
                all_chunk_ids.extend(ids)
                retrieved_contexts.append(result)
                messages.append({"role": "tool", "content": result})

        logger.warning(
            "Max tool calls (%d) reached — falling back to direct generation.", self.max_tool_calls
        )
        return self.generate(topic, retrieved_contexts), all_chunk_ids

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_topics(self) -> list[str]:
        """Return every distinct topic stored in the collection."""
        result = self._collection.get(include=["metadatas"])
        seen: set[str] = set()
        topics: list[str] = []
        for meta in result["metadatas"]:
            t = meta["topic"]
            if t not in seen:
                seen.add(t)
                topics.append(t)
        return topics

    def retrieve(self, topic: str) -> tuple[list[str], list[str]]:
        """Embed topic, query Chroma with topic filter. Returns (documents, chunk_ids)."""
        try:
            resp = ollama.embeddings(model=self.embed_model, prompt=topic)
        except Exception as exc:
            raise RuntimeError(
                f"Ollama embedding failed — is Ollama running at {config.OLLAMA_BASE_URL}? ({exc})"
            ) from exc
        results = self._collection.query(
            query_embeddings=[resp["embedding"]],
            n_results=self.top_k,
            where={"topic": topic},
        )
        return results["documents"][0], results["ids"][0]

    def generate(self, topic: str, documents: list[str]) -> AgentOutput:
        """Call Ollama with schema-enforced structured output."""
        context = "\n\n---\n\n".join(documents)
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT.format(course=self.course_name)},
            {"role": "user", "content": f"Topic: {topic}\n\nExcerpts:\n{context}"},
        ]

        stop = threading.Event()
        threading.Thread(target=self._heartbeat, args=(stop,), daemon=True).start()
        try:
            resp = ollama.chat(
                model=self.gen_model,
                messages=messages,
                format=AgentOutput.model_json_schema(),
                options={"temperature": 0.4, "num_predict": 600},
            )
        except Exception as exc:
            raise RuntimeError(
                f"Ollama generation failed — is Ollama running at {config.OLLAMA_BASE_URL}? ({exc})"
            ) from exc
        finally:
            stop.set()

        return AgentOutput.model_validate_json(resp.message.content)

    def run(self, topic: str) -> tuple[AgentOutput, list[str]]:
        """Full pipeline. Agentic: LLM retrieves via tool calls. Non-agentic: pre-fetched chunks."""
        if self.agentic:
            logger.info("Agentic mode — LLM will decide what to retrieve.")
            stop = threading.Event()
            threading.Thread(target=self._heartbeat, args=(stop,), daemon=True).start()
            try:
                return self._agentic_run(topic)
            finally:
                stop.set()

        documents, chunk_ids = self.retrieve(topic)
        logger.info("Retrieved %d chunks. Calling LLM...", len(documents))
        output = self.generate(topic, documents)
        return output, chunk_ids


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    agent = Agent()
    test_topic = "Phase 3 — Data & Features (~10 min, high priority)"
    print(f"Mode  : {'agentic (LLM chooses queries)' if agent.agentic else 'non-agentic (pre-fetched chunks)'}")
    print(f"Model : {agent.gen_model}")
    print()
    output, chunk_ids = agent.run(test_topic)
    print(f"Anecdote:\n{output.anecdote}\n")
    print(f"Key takeaway:\n{output.key_takeaway}\n")
    label = "Chunks LLM retrieved" if agent.agentic else "Chunks used"
    print(f"{label}: {chunk_ids}")
