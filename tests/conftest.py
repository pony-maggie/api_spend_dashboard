from pathlib import Path

import pytest


@pytest.fixture
def temp_db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.sqlite3'}"
