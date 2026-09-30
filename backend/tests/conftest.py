""" conftest.py — shared pytest fixtures and path setup.

The application package (`src`) lives under `backend/` and is imported as
`from src.<module> import ...` (the CLI/API run from inside `backend/`).
We add that directory to sys.path so the tests can import the same way.
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture
def write_file(tmp_path):
    """Return a helper that writes `content` to `name` under tmp_path and
    returns the absolute path."""
    def _write(name: str, content: str = "hello world", encoding: str = "utf-8") -> str:
        p = tmp_path / name
        p.write_text(content, encoding=encoding)
        return str(p)
    return _write


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A Flask test client with the DB forced unreachable and JSON storage
    redirected into a temp dir, so tests never touch a real database or the
    repo's own output/ directory."""
    import app as app_module

    monkeypatch.setattr(app_module.repository, "_get_connection", lambda: None)
    monkeypatch.setattr(app_module.repository, "json_dir", str(tmp_path / "scans"))
    monkeypatch.setattr(app_module.audit, "_get_connection", lambda: None)
    monkeypatch.setattr(app_module.audit, "log_path", str(tmp_path / "audit.log"))
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()
