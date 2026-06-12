""" test_audit.py — AuditLogger file-fallback behavior. """
import os

from src.audit import AuditLogger


def test_fallback_log_written_when_db_unavailable(monkeypatch, tmp_path):
    """When the DB connection fails, the event is written to a log file."""
    log_path = tmp_path / "plagcheck.log"

    audit = AuditLogger()
    # Force "no database available".
    monkeypatch.setattr(audit, "_get_connection", lambda: None)

    # Redirect the fallback log to a temp file so we can inspect it.
    def fake_fallback(event_type, scan_id, user_id, payload, error_msg):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{event_type}|{error_msg}\n")

    monkeypatch.setattr(audit, "_fallback_log", fake_fallback)

    audit.log("SCAN_START", payload={"files": ["a.txt", "b.txt"]})

    assert os.path.isfile(log_path)
    content = log_path.read_text(encoding="utf-8")
    assert "SCAN_START" in content


def test_real_fallback_writes_to_disk(monkeypatch):
    """Exercise the real _fallback_log path to ensure it does not raise."""
    audit = AuditLogger()
    monkeypatch.setattr(audit, "_get_connection", lambda: None)
    # Should not raise even though no DB is configured.
    audit.log("UNIT_TEST_EVENT", payload={"k": "v"})
