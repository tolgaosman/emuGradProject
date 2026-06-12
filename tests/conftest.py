""" conftest.py — shared pytest fixtures and path setup.

The application package (`src`) lives under `plagcheck/` and is imported as
`from src.<module> import ...` (the CLI/API run from inside `plagcheck/`).
We add that directory to sys.path so the tests can import the same way.
"""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAGCHECK_DIR = os.path.join(REPO_ROOT, "plagcheck")

if PLAGCHECK_DIR not in sys.path:
    sys.path.insert(0, PLAGCHECK_DIR)


@pytest.fixture
def write_file(tmp_path):
    """Return a helper that writes `content` to `name` under tmp_path and
    returns the absolute path."""
    def _write(name: str, content: str = "hello world", encoding: str = "utf-8") -> str:
        p = tmp_path / name
        p.write_text(content, encoding=encoding)
        return str(p)
    return _write
