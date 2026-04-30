"""
Orchestrator: runs the full daily pipeline end-to-end.

Usage:
  python run_daily.py             # full run — retrieves, generates, emails, logs
  python run_daily.py --dry-run   # skips sending email; prints output to stdout
"""
import argparse
import logging
import random

import chromadb

import config
from pipeline import agent, memory, send_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_all_topics() -> list[str]:
    """Return every distinct topic stored in the Chroma collection."""
    client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
    collection = client.get_collection(config.COLLECTION_NAME)
    result = collection.get(include=["metadatas"])
    seen: set[str] = set()
    topics: list[str] = []
    for meta in result["metadatas"]:
        t = meta["topic"]
        if t not in seen:
            seen.add(t)
            topics.append(t)
    return topics


def pick_topic() -> str:
    """
    Pick a topic not sent within RECENCY_DAYS.
    Falls back to the least-recently-used topic when the full rotation is complete.
    """
    all_topics = get_all_topics()
    recent = set(memory.get_recent_topics())
    available = [t for t in all_topics if t not in recent]

    if available:
        return random.choice(available)

    logger.info("All %d topics covered recently — falling back to LRU.", len(all_topics))
    return memory.get_least_recently_used_topic(all_topics)


def main(dry_run: bool = False) -> None:
    logger.info("=== Daily run started (dry_run=%s) ===", dry_run)

    memory.init_db()

    topic = pick_topic()
    logger.info("Selected topic: %s", topic)

    output, chunk_ids = agent.run(topic)
    logger.info(
        "Generated — anecdote: %d chars, question: %d chars",
        len(output.anecdote),
        len(output.question),
    )

    if dry_run:
        print("\n--- DRY RUN OUTPUT ---")
        print(f"Topic:    {topic}")
        print(f"\nAnecdote: {output.anecdote}")
        print(f"\nQuestion: {output.question}")
        print(f"\nChunks:   {chunk_ids}")
        print("--- (email not sent) ---\n")
    else:
        html = send_email._build_email_html(output.anecdote, output.question, topic)
        send_email.send(
            subject=f"Interview Prep — {topic}",
            body_html=html,
            body_text=f"{output.anecdote}\n\n{output.question}",
        )
        logger.info("Email sent.")

    memory.log_run(
        topic=topic,
        chunk_ids=chunk_ids,
        anecdote=output.anecdote,
        question=output.question,
    )
    logger.info("=== Daily run complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interview agent daily run")
    parser.add_argument("--dry-run", action="store_true", help="Skip sending email")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
