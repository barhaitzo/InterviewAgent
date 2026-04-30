"""
End-to-end tests. Require live services — skip by default.

Run with:
  pytest tests/ -m e2e -v -s
"""
import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.e2e


def test_email_send():
    """Actually delivers a message to the configured inbox via Gmail SMTP."""
    from pipeline.email_sender import EmailSender
    print("\n  Connecting to Gmail SMTP...", flush=True)
    sender = EmailSender()
    sender.send(
        subject="[E2E TEST] Interview Agent",
        body_html="<p>E2E test from pytest — SMTP is working.</p>",
        body_text="E2E test from pytest — SMTP is working.",
    )
    print("  Email delivered.", flush=True)


def test_agent_retrieve():
    """Embeds a real topic and retrieves chunks from the live ChromaDB collection."""
    from pipeline.agent import Agent
    print("\n  Loading ChromaDB collection...", flush=True)
    agent = Agent()
    topics = agent.get_all_topics()
    assert topics, "ChromaDB collection is empty — run ingest.py first"
    print(f"  Found {len(topics)} topics. Embedding '{topics[0]}'...", flush=True)
    docs, ids = agent.retrieve(topics[0])
    assert len(docs) > 0
    assert len(ids) == len(docs)
    print(f"  Retrieved {len(docs)} chunk(s). OK.", flush=True)


def test_agent_full_run():
    """Full retrieve → Ollama generate → parse cycle against live services."""
    from pipeline.agent import Agent
    print("\n  Loading agent...", flush=True)
    agent = Agent()
    topics = agent.get_all_topics()
    assert topics, "ChromaDB collection is empty — run ingest.py first"
    topic = topics[0]
    print(f"  Topic: '{topic}'", flush=True)
    print("  Calling Ollama (this may take 30–60s)...", flush=True)
    output, chunk_ids = agent.run(topic)
    assert output.anecdote
    assert output.question
    assert len(chunk_ids) > 0
    print(f"  Anecdote: {output.anecdote[:80]}...", flush=True)
    print(f"  Question: {output.question[:80]}...", flush=True)


def test_full_dry_run(capsys):
    """Runs the complete daily pipeline (topic pick → generate → log) without sending email."""
    from run_daily import main
    print("\n  Running full pipeline in dry-run mode...", flush=True)
    with capsys.disabled():
        main(dry_run=True)
    print("  Pipeline complete.", flush=True)
