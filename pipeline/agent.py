"""
Generation agent: retrieve relevant chunks from Chroma, call Ollama, parse JSON.

Run: python agent.py
"""
import json
import logging
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chromadb
import ollama
from pydantic import BaseModel, ValidationError

import config

logger = logging.getLogger(__name__)

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


class AgentOutput(BaseModel):
    anecdote: str
    question: str


def _parse_output(raw: str) -> AgentOutput:
    """Strip markdown code fences if present, then parse JSON into AgentOutput."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first line (```json or ```) and last line (```)
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()
    # Locate outermost JSON object in case of leading/trailing prose
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return AgentOutput(**json.loads(text))


def retrieve(topic: str) -> tuple[list[str], list[str]]:
    """
    Embed the topic string and retrieve top-k chunks filtered to that topic.
    Returns (documents, chunk_ids).
    """
    client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
    collection = client.get_collection(config.COLLECTION_NAME)

    resp = ollama.embeddings(model=config.EMBED_MODEL, prompt=topic)
    embedding = resp["embedding"]

    results = collection.query(
        query_embeddings=[embedding],
        n_results=config.TOP_K,
        where={"topic": topic},
    )
    return results["documents"][0], results["ids"][0]


def _heartbeat(stop: threading.Event, interval: int = 15) -> None:
    elapsed = 0
    while not stop.wait(interval):
        elapsed += interval
        logger.info("  ... LLM still generating (%ds elapsed)", elapsed)


def generate(topic: str, documents: list[str]) -> AgentOutput:
    """
    Format prompt, call Ollama, parse + validate JSON.
    Retries once if the first response is not valid JSON.
    Logs a heartbeat every 15s so the log never looks hung.
    """
    context = "\n\n---\n\n".join(documents)
    user_content = f"Topic: {topic}\n\nExcerpts:\n{context}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    stop = threading.Event()
    threading.Thread(target=_heartbeat, args=(stop,), daemon=True).start()
    try:
        resp = ollama.chat(
            model=config.GEN_MODEL,
            messages=messages,
            options={"temperature": 0.4},
        )
        raw = resp.message.content
    finally:
        stop.set()


    try:
        return _parse_output(raw)
    except (json.JSONDecodeError, ValidationError, KeyError) as exc:
        logger.warning("Parse failed on first attempt (%s) — retrying.", exc)
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
        resp2 = ollama.chat(
            model=config.GEN_MODEL,
            messages=messages,
            options={"temperature": 0.2},
        )
        return _parse_output(resp2.message.content)


def run(topic: str) -> tuple[AgentOutput, list[str]]:
    """Full retrieve → generate pipeline. Returns (output, chunk_ids_used)."""
    documents, chunk_ids = retrieve(topic)
    logger.info("Retrieved %d chunks. Calling LLM...", len(documents))
    output = generate(topic, documents)
    return output, chunk_ids


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    test_topic = "Phase 3 — Data & Features (~10 min, high priority)"
    output, chunk_ids = run(test_topic)
    print(f"Anecdote:\n{output.anecdote}\n")
    print(f"Question:\n{output.question}\n")
    print(f"Chunks used: {chunk_ids}")
