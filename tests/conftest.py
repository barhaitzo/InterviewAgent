import pytest
from pathlib import Path


def pytest_collection_modifyitems(config, items):
    """Skip e2e-marked tests unless -m e2e is explicitly requested."""
    try:
        markexpr = config.getoption("-m") or ""
    except ValueError:
        markexpr = ""
    if "e2e" not in markexpr:
        skip = pytest.mark.skip(reason="E2E test — run with: pytest -m e2e")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip)

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
