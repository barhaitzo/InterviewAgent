import pytest
from pathlib import Path
from unittest.mock import patch

from pipeline.ingest import Ingester


def make_ingester(tmp_path: Path, sample_md_file: Path, **kwargs) -> Ingester:
    with patch("chromadb.PersistentClient"):
        return Ingester(
            source_path=sample_md_file,
            chroma_path=tmp_path / "chroma",
            **kwargs,
        )


# ---------------------------------------------------------------------------
# _split_long_text
# ---------------------------------------------------------------------------

class TestSplitLongText:
    def test_short_text_returned_unchanged(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        assert ing._split_long_text("hello world") == ["hello world"]

    def test_long_text_produces_multiple_parts(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        ing.max_chars = 50
        ing.overlap_chars = 10
        parts = ing._split_long_text("A" * 200)
        assert len(parts) > 1

    def test_no_empty_parts(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        ing.max_chars = 50
        ing.overlap_chars = 10
        text = "\n".join(["word"] * 40)
        assert all(p for p in ing._split_long_text(text))

    def test_all_content_covered(self, tmp_path, sample_md_file):
        """Every character in the original text must appear in at least one part."""
        ing = make_ingester(tmp_path, sample_md_file)
        ing.max_chars = 60
        ing.overlap_chars = 15
        text = "abcde " * 30
        parts = ing._split_long_text(text)
        combined = " ".join(parts)
        for word in text.split():
            assert word in combined

    def test_infinite_loop_guard_no_newlines(self, tmp_path, sample_md_file):
        """Text with no newlines and large overlap must still terminate."""
        ing = make_ingester(tmp_path, sample_md_file)
        ing.max_chars = 20
        ing.overlap_chars = 18
        parts = ing._split_long_text("x" * 100)
        assert len(parts) > 1
        assert all(p for p in parts)

    def test_empty_string_returns_empty_list(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        assert ing._split_long_text("") == []


# ---------------------------------------------------------------------------
# _chunk_id
# ---------------------------------------------------------------------------

class TestChunkId:
    def test_deterministic(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        assert ing._chunk_id("heading", 0) == ing._chunk_id("heading", 0)

    def test_different_heading_gives_different_id(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        assert ing._chunk_id("A", 0) != ing._chunk_id("B", 0)

    def test_different_index_gives_different_id(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        assert ing._chunk_id("A", 0) != ing._chunk_id("A", 1)

    def test_returns_16_character_string(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        assert len(ing._chunk_id("heading", 0)) == 16


# ---------------------------------------------------------------------------
# parse_chunks
# ---------------------------------------------------------------------------

class TestParseChunks:
    def test_returns_at_least_one_chunk(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        assert len(ing.parse_chunks()) > 0

    def test_topic_is_h2_heading(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        topics = {c["metadata"]["topic"] for c in ing.parse_chunks()}
        assert "Feature Stores" in topics
        assert "Data Pipelines" in topics

    def test_heading_path_includes_h3(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        paths = {c["metadata"]["heading_path"] for c in ing.parse_chunks()}
        assert any("Batch vs Streaming" in p for p in paths)

    def test_all_required_metadata_keys_present(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        for chunk in ing.parse_chunks():
            assert {"id", "document", "metadata"} <= chunk.keys()
            assert {"topic", "heading_path", "chunk_index", "source"} <= chunk["metadata"].keys()

    def test_chunk_ids_are_unique(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        ids = [c["id"] for c in ing.parse_chunks()]
        assert len(ids) == len(set(ids))

    def test_source_filename_in_metadata(self, tmp_path, sample_md_file):
        ing = make_ingester(tmp_path, sample_md_file)
        for chunk in ing.parse_chunks():
            assert chunk["metadata"]["source"] == sample_md_file.name

    def test_h1_only_doc_uses_h1_as_topic(self, tmp_path):
        md = tmp_path / "h1only.md"
        md.write_text("# Top Level\n\nsome content here\n", encoding="utf-8")
        with patch("chromadb.PersistentClient"):
            ing = Ingester(source_path=md, chroma_path=tmp_path / "chroma")
        chunks = ing.parse_chunks()
        assert all(c["metadata"]["topic"] == "Top Level" for c in chunks)
