""" test_audit.py — AuditLogger file-fallback behavior. """
import os
from unittest.mock import MagicMock

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


def test_log_writes_to_db_when_available(monkeypatch):
    """log() inserts a row and commits when a DB connection succeeds."""
    audit = AuditLogger()

    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = (42,)  # resolved internal scan_id
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    monkeypatch.setattr(audit, "_get_connection", lambda: fake_conn)

    audit.log("SCAN_COMPLETE", scan_uuid="some-uuid", payload={"flagged_count": 2})

    fake_conn.commit.assert_called_once()
    fake_conn.close.assert_called_once()
    insert_calls = [c for c in fake_cursor.execute.call_args_list if "audit_log" in c.args[0]]
    assert len(insert_calls) == 1
    _, params = insert_calls[0].args
    scan_id, _user_id, event_type, _detail = params
    assert scan_id == 42
    assert event_type == "SCAN_COMPLETE"


def test_log_falls_back_when_db_write_raises(monkeypatch):
    """A DB error mid-write still reaches the fallback log, not an exception."""
    audit = AuditLogger()

    fake_conn = MagicMock()
    fake_conn.cursor.side_effect = RuntimeError("boom")
    monkeypatch.setattr(audit, "_get_connection", lambda: fake_conn)

    calls = []
    monkeypatch.setattr(
        audit,
        "_fallback_log",
        lambda event_type, scan_uuid, user_id, payload, error_msg: calls.append(event_type),
    )

    audit.log("SCAN_START", scan_uuid="uuid-x")
    assert calls == ["SCAN_START"]
    fake_conn.close.assert_called_once()


def test_resolve_scan_id_returns_none_without_uuid():
    """_resolve_scan_id short-circuits to None when no scan_uuid is given."""
    audit = AuditLogger()
    assert audit._resolve_scan_id(MagicMock(), None) is None
