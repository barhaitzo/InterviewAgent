"""
Orchestrator: runs the full daily pipeline end-to-end.

Usage:
  python run_daily.py             # full run — retrieves, generates, emails, logs
  python run_daily.py --dry-run   # skips sending email; prints output to stdout
"""
import argparse
import logging
import random

import config
from pipeline import Agent, EmailSender, Memory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def pick_topic(agent: Agent, memory: Memory) -> str:
    """Pick a topic not sent within RECENCY_DAYS; fall back to LRU when all are covered."""
    all_topics = agent.get_all_topics()
    if not all_topics:
        raise RuntimeError(
            "No topics found in ChromaDB — run 'python pipeline/ingest.py' first."
        )

    recent = set(memory.get_recent_topics())
    available = [t for t in all_topics if t not in recent]

    if available:
        return random.choice(available)

    logger.info("All %d topics covered recently — falling back to LRU.", len(all_topics))
    return memory.get_lru_topic(all_topics)


def main(dry_run: bool = False) -> None:
    logger.info("=== Daily run started (dry_run=%s) ===", dry_run)

    try:
        agent = Agent()
        memory = Memory()

        topic = pick_topic(agent, memory)
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
            sender = EmailSender()
            sender.send(
                subject=f"Interview Prep — {topic}",
                body_html=EmailSender.build_html(output.anecdote, output.question, topic, agent.gen_model),
                body_text=f"{output.anecdote}\n\n{output.question}",
            )
            logger.info("Email sent.")

        memory.log_run(
            topic=topic,
            chunk_ids=chunk_ids,
            anecdote=output.anecdote,
            question=output.question,
        )

    except Exception:
        logger.exception("=== Daily run FAILED ===")
        raise

    logger.info("=== Daily run complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interview agent daily run")
    parser.add_argument("--dry-run", action="store_true", help="Skip sending email")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
