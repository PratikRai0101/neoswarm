"""Tests for backend data-directory selection."""

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_data_directory_override_wins_over_defaults(tmp_path):
    """Automation can isolate all persisted state without patching modules."""
    data_dir = tmp_path / "neoswarm-data"
    env = {
        **os.environ,
        "NEOSWARM_DATA_DIR": str(data_dir),
        "PYTHONPATH": str(PROJECT_ROOT),
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from backend.config.paths import DATA_ROOT; print(DATA_ROOT)",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == str(data_dir)
