import os
import shutil
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TESTS_DIR        = Path(__file__).parent
FIXTURES_DIR     = TESTS_DIR / "fixtures"
OUTPUT_DIR       = TESTS_DIR / "output"
TEST_CONFIG_PATH = TESTS_DIR / "test_config.yaml"

TEST_VIDEO_ID    = "7234217708424826139"
TEST_VIDEO_URL   = "https://www.tiktok.com/@frances.con.romeo/video/7234217708424826139"
TEST_CHANNEL_URL = "https://www.tiktok.com/@frances.con.romeo"

FIXTURE_DIR = FIXTURES_DIR / TEST_VIDEO_ID

# ---------------------------------------------------------------------------
# Pipeline step order — used by test_pipeline.py to know what to run/skip
# ---------------------------------------------------------------------------
PIPELINE_STEPS = ["download", "stt", "punctuation", "alignment", "srt_merge", "translation"]

# ---------------------------------------------------------------------------
# Custom CLI option: --from-step
# ---------------------------------------------------------------------------
def pytest_addoption(parser):
    parser.addoption(
        "--from-step",
        action="store",
        default=None,
        help=(
            "Run the pipeline from this step onward using saved fixtures. "
            f"Valid values: {', '.join(PIPELINE_STEPS)}"
        ),
    )

@pytest.fixture(scope="session")
def from_step(request):
    """Returns the value of --from-step, or None (meaning full pipeline)."""
    value = request.config.getoption("--from-step")
    if value is not None and value not in PIPELINE_STEPS:
        pytest.fail(
            f"Invalid --from-step value '{value}'. "
            f"Valid steps: {', '.join(PIPELINE_STEPS)}"
        )
    return value

# ---------------------------------------------------------------------------
# Shared session fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def clean_output_dir():
    """Delete and recreate tests/output/ before the test session."""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    yield
    # Output is left in place after tests so you can inspect artifacts.

@pytest.fixture(scope="session")
def test_config(clean_output_dir):
    """
    Load the test config, set TK_CONFIG_FILE, and initialize the DB.
    Depends on clean_output_dir so the output directory exists before init_db.
    """
    os.environ["TK_CONFIG_FILE"] = str(TEST_CONFIG_PATH.resolve())
    from tk_orchestrator.config import load_config
    from tk_orchestrator.db import init_db
    config = load_config()
    init_db(config)
    return config

@pytest.fixture(scope="session")
def db_session(test_config):
    """Create a raw SQLite session for direct DB queries in tests."""
    from tk_orchestrator.db import get_engine
    from sqlalchemy.orm import Session
    session = Session(get_engine())
    yield session
    session.close()
