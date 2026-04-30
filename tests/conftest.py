import pytest
from pathlib import Path

SAMPLE_MD = """\
# ML System Design

## Feature Stores

Feature stores provide a central repository for ML features.
They enable feature reuse across teams and models.
Offline stores use batch pipelines; online stores serve low-latency requests.

## Data Pipelines

Data pipelines transform raw data into features.
They must handle schema evolution, late data, and backfills.

### Batch vs Streaming

Batch pipelines run on a schedule.
Streaming pipelines process events in real time.
"""


@pytest.fixture
def sample_md_file(tmp_path: Path) -> Path:
    p = tmp_path / "test_doc.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    return p


@pytest.fixture
def tmp_chroma_path(tmp_path: Path) -> Path:
    return tmp_path / "chroma_db"


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "history.db"
