"""Retrieval-augmented generation agent: retrieve chunks, call LLM, parse output."""
import json
import logging
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chromadb
import ollama
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

import config

load_dotenv()

logger = logging.getLogger(__name__)


class AgentOutput(BaseModel):
    anecdote: str
    question: str


class Agent:
    SYSTEM_PROMPT = """\
You are an interview prep assistant. Given excerpts from a personal ML system design \
crash course, produce ONE concise concept refresher (3-5 sentences) and ONE thoughtful \
interview question that probes understanding of that concept.

Constraints:
- Ground both outputs strictly in the provided excerpts.
- Do not invent company names, statistics, or external facts.
- Refresher should be memorable and tight — no fluff.
- Question should be open-ended (not yes/no).

Output ONLY valid JSON: {"anecdote": "...", "question": "..."}\
"""

    def __init__(
        self,
        chroma_path: Path = config.CHROMA_PATH,
        collection_name: str = config.COLLECTION_NAME,
        embed_model: str = config.EMBED_MODEL,
        gen_model: str = config.GEN_MODEL,
        gen_provider: str = config.GEN_PROVIDER,
        top_k: int = config.TOP_K,
    ) -> None:
        self.embed_model = embed_model
        self.gen_model = gen_model
        self.gen_provider = gen_provider.lower()
        self.top_k = top_k
        self._client = chromadb.PersistentClient(path=str(chroma_path))
        try:
            self._collection = self._client.get_collection(collection_name)
        except Exception as exc:
            raise RuntimeError(
                f"ChromaDB collection '{collection_name}' not found. "
                "Run 'python pipeline/ingest.py' first."
            ) from exc

    # ------------------------------------------------------------------
    # Internal — parsing
    # ------------------------------------------------------------------

    def _parse_output(self, raw: str) -> AgentOutput:
        """Strip markdown code fences if present, then parse JSON into AgentOutput."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(inner).strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]
        return AgentOutput(**json.loads(text))

    def _heartbeat(self, stop: threading.Event, interval: int = 15) -> None:
        elapsed = 0
        while not stop.wait(interval):
            elapsed += interval
            logger.info("  ... LLM still generating (%ds elapsed)", elapsed)

    # ------------------------------------------------------------------
    # Internal — provider dispatch
    # ------------------------------------------------------------------

    def _call_ollama(self, messages: list[dict], temperature: float = 0.4) -> str:
        try:
            resp = ollama.chat(
                model=self.gen_model,
                messages=messages,
                options={"temperature": temperature},
            )
            return resp.message.content
        except Exception as exc:
            raise RuntimeError(
                f"Ollama generation failed — is Ollama running at {config.OLLAMA_BASE_URL}? ({exc})"
            ) from exc

    def _call_anthropic(self, messages: list[dict], temperature: float = 0.4) -> str:
        try:
            import anthropic as _anthropic
        except ImportError:
            logger.warning("anthropic package not installed — falling back to Ollama.")
            return self._call_ollama(messages, temperature)

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set — falling back to Ollama.")
            return self._call_ollama(messages, temperature)

        try:
            client = _anthropic.Anthropic(api_key=api_key)
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_messages = [m for m in messages if m["role"] != "system"]
            resp = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=1024,
                system=system,
                messages=user_messages,
                temperature=temperature,
            )
            return resp.content[0].text
        except _anthropic.APIError as exc:
            logger.warning("Anthropic API unavailable (%s) — falling back to Ollama.", exc)
            return self._call_ollama(messages, temperature)

    def _call_openai(self, messages: list[dict], temperature: float = 0.4) -> str:
        try:
            import openai as _openai
        except ImportError:
            logger.warning("openai package not installed — falling back to Ollama.")
            return self._call_ollama(messages, temperature)

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — falling back to Ollama.")
            return self._call_ollama(messages, temperature)

        try:
            client = _openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                temperature=temperature,
            )
            return resp.choices[0].message.content
        except _openai.APIError as exc:
            logger.warning("OpenAI API unavailable (%s) — falling back to Ollama.", exc)
            return self._call_ollama(messages, temperature)

    def _call_provider(self, messages: list[dict], temperature: float = 0.4) -> str:
        """Dispatch to the configured provider, falling back to Ollama on failure."""
        if self.gen_provider == "anthropic":
            return self._call_anthropic(messages, temperature)
        if self.gen_provider == "openai":
            return self._call_openai(messages, temperature)
        return self._call_ollama(messages, temperature)

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
        """Call the configured LLM provider, parse JSON output. Retries once on parse failure."""
        context = "\n\n---\n\n".join(documents)
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"Topic: {topic}\n\nExcerpts:\n{context}"},
        ]

        stop = threading.Event()
        threading.Thread(target=self._heartbeat, args=(stop,), daemon=True).start()
        try:
            raw = self._call_provider(messages, temperature=0.4)
        finally:
            stop.set()

        try:
            return self._parse_output(raw)
        except (json.JSONDecodeError, ValidationError, KeyError) as exc:
            logger.warning("Parse failed (%s) — retrying.", exc)
            messages += [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"Your previous output was invalid. Error: {exc}\n"
                        'Output ONLY valid JSON: {"anecdote": "...", "question": "..."}'
                    ),
                },
            ]
            raw2 = self._call_provider(messages, temperature=0.2)
            return self._parse_output(raw2)

    def run(self, topic: str) -> tuple[AgentOutput, list[str]]:
        """Full retrieve → generate pipeline. Returns (output, chunk_ids_used)."""
        documents, chunk_ids = self.retrieve(topic)
        logger.info("Retrieved %d chunks. Calling LLM (%s)...", len(documents), self.gen_provider)
        output = self.generate(topic, documents)
        return output, chunk_ids


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    agent = Agent()
    test_topic = "Phase 3 — Data & Features (~10 min, high priority)"
    output, chunk_ids = agent.run(test_topic)
    print(f"Anecdote:\n{output.anecdote}\n")
    print(f"Question:\n{output.question}\n")
    print(f"Chunks used: {chunk_ids}")
