""" test_repository.py — ScanRepository persistence and JSON fallback. """
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.engine import ScanResult
from src.matrix import ComparisonMatrix
from src.repository import ScanRepository


def _matrix() -> ComparisonMatrix:
    m = ComparisonMatrix(["a.txt", "b.txt", "c.txt"])
    m.set(0, 1, 0.9)
    m.set(0, 2, 0.2)
    m.set(1, 2, 0.3)
    return m


def _result() -> ScanResult:
    return ScanResult(mode="text_similarity", names=["a.txt", "b.txt", "c.txt"], matrix=_matrix())


def _files_meta() -> list[dict]:
    return [
        {"file_name": "a.txt", "file_size_bytes": 10, "file_format": "txt"},
        {"file_name": "b.txt", "file_size_bytes": 20, "file_format": "txt"},
        {"file_name": "c.txt", "file_size_bytes": 30, "file_format": "txt"},
    ]


def test_json_fallback_round_trip(tmp_path, monkeypatch):
    """When PostgreSQL is unreachable, save/get round-trips through JSON."""
    repo = ScanRepository(json_dir=str(tmp_path))
    monkeypatch.setattr(repo, "_get_connection", lambda: None)

    scan_uuid = repo.save_scan("text_similarity", 0.70, _files_meta(), _result())
    record = repo.get_scan(scan_uuid)
    assert record is not None
    assert record["scan_uuid"] == scan_uuid
    assert record["algorithm"] == "text_similarity"
    assert record["threshold"] == 0.70
    assert len(record["files"]) == 3
    assert len(record["pairs"]) == 3

    flagged = [p for p in record["pairs"] if p["flagged"]]
    assert len(flagged) == 1
    assert {flagged[0]["file_a"], flagged[0]["file_b"]} == {"a.txt", "b.txt"}


def test_get_scan_missing_returns_none(tmp_path, monkeypatch):
    """A scan_uuid with no DB row and no JSON file returns None."""
    repo = ScanRepository(json_dir=str(tmp_path))
    monkeypatch.setattr(repo, "_get_connection", lambda: None)
    assert repo.get_scan("00000000-0000-0000-0000-000000000000") is None


def test_save_scan_generates_uuid_when_omitted(tmp_path, monkeypatch):
    """save_scan() mints its own scan_uuid when the caller doesn't supply one."""
    repo = ScanRepository(json_dir=str(tmp_path))
    monkeypatch.setattr(repo, "_get_connection", lambda: None)

    scan_uuid = repo.save_scan("text_similarity", 0.5, _files_meta(), _result())
    assert scan_uuid
    assert repo.get_scan(scan_uuid) is not None


def test_save_db_orders_pair_ids_ascending():
    """scan_pair rows must satisfy file_id_a < file_id_b regardless of insert order."""
    repo = ScanRepository()

    fake_cursor = MagicMock()
    # Sequence of fetchone() results: system user lookup, scan_request insert,
    # then one insert per file (a.txt gets the *higher* id on purpose, to
    # force the swap branch in _save_db).
    fake_cursor.fetchone.side_effect = [(1,), (10,), (30,), (20,)]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor

    m = ComparisonMatrix(["a.txt", "b.txt"])
    m.set(0, 1, 0.95)
    result = ScanResult(mode="text_similarity", names=["a.txt", "b.txt"], matrix=m)
    record = repo._build_record(
        "uuid-1",
        "text_similarity",
        0.70,
        [
            {"file_name": "a.txt", "file_size_bytes": 10, "file_format": "txt"},
            {"file_name": "b.txt", "file_size_bytes": 10, "file_format": "txt"},
        ],
        result,
    )

    repo._save_db(fake_conn, record)

    pair_calls = [c for c in fake_cursor.execute.call_args_list if "scan_pair" in c.args[0]]
    assert len(pair_calls) == 1
    _, params = pair_calls[0].args
    _, id_a, id_b, _score, _flagged = params
    assert id_a < id_b
    assert {id_a, id_b} == {20, 30}


def test_load_db_reconstructs_record_from_rows(monkeypatch):
    """get_scan() rebuilds the full record shape from mocked DB rows."""
    repo = ScanRepository()

    fake_cursor = MagicMock()
    fake_cursor.fetchone.side_effect = [
        (10, 0.70, "complete", datetime(2026, 1, 1, 12, 0, 0)),  # scan_request row
    ]
    fake_cursor.fetchall.side_effect = [
        [("text_similarity",)],  # scan_algorithm rows
        [(1, "a.txt", 100, "txt", 0.5), (2, "b.txt", 200, "txt", None)],  # scan_file rows
        [(1, 2, 0.9, True)],  # scan_pair rows
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    monkeypatch.setattr(repo, "_get_connection", lambda: fake_conn)

    record = repo.get_scan("uuid-1")
    assert record is not None
    assert record["scan_uuid"] == "uuid-1"
    assert record["algorithm"] == "text_similarity"
    assert record["threshold"] == 0.70
    assert len(record["files"]) == 2
    assert record["files"][0]["similarity_index"] == 0.5
    assert record["files"][1]["similarity_index"] is None
    assert record["pairs"] == [
        {"file_a": "a.txt", "file_b": "b.txt", "score": 0.9, "flagged": True}
    ]
    fake_conn.close.assert_called_once()


def test_load_db_reconstructs_algorithm_override(monkeypatch):
    """A forced single algorithm is stored as a second scan_algorithm row and
    surfaces as `algorithm_override` on read, distinct from the mode name."""
    repo = ScanRepository()

    fake_cursor = MagicMock()
    fake_cursor.fetchone.side_effect = [
        (10, 0.70, "complete", datetime(2026, 1, 1, 12, 0, 0)),
    ]
    fake_cursor.fetchall.side_effect = [
        [("text_similarity",), ("cosine",)],  # mode row + forced-algorithm row
        [(1, "a.txt", 100, "txt", None), (2, "b.txt", 200, "txt", None)],
        [(1, 2, 0.9, True)],
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    monkeypatch.setattr(repo, "_get_connection", lambda: fake_conn)

    record = repo.get_scan("uuid-override")
    assert record is not None
    assert record["algorithm"] == "text_similarity"
    assert record["algorithm_override"] == "cosine"


def test_load_db_returns_none_when_scan_not_found(monkeypatch):
    """get_scan() falls through to the JSON path when the DB has no row."""
    repo = ScanRepository()

    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = None
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    monkeypatch.setattr(repo, "_get_connection", lambda: fake_conn)

    assert repo.get_scan("does-not-exist") is None


def test_get_or_create_system_user_inserts_when_absent():
    """The system user row is created on first use if it doesn't exist yet."""
    repo = ScanRepository()

    fake_cursor = MagicMock()
    fake_cursor.fetchone.side_effect = [None, (7,)]  # no existing row, then new id
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor

    user_id = repo._get_or_create_system_user(fake_conn)
    assert user_id == 7
    insert_calls = [
        c for c in fake_cursor.execute.call_args_list if "INSERT INTO app_user" in c.args[0]
    ]
    assert len(insert_calls) == 1


def test_save_scan_falls_back_to_json_on_db_error(tmp_path, monkeypatch):
    """A DB write failure mid-transaction still leaves a retrievable JSON record."""
    repo = ScanRepository(json_dir=str(tmp_path))

    fake_conn = MagicMock()
    fake_conn.cursor.side_effect = RuntimeError("boom")
    monkeypatch.setattr(repo, "_get_connection", lambda: fake_conn)

    scan_uuid = repo.save_scan("text_similarity", 0.70, _files_meta(), _result())
    fake_conn.rollback.assert_called_once()

    # get_scan should now read from JSON since the DB mock has no real data.
    monkeypatch.setattr(repo, "_get_connection", lambda: None)
    record = repo.get_scan(scan_uuid)
    assert record is not None
    assert record["scan_uuid"] == scan_uuid


def _uuid() -> str:
    import uuid

    return str(uuid.uuid4())


def test_list_scans_summarizes_json_records(tmp_path, monkeypatch):
    repo = ScanRepository(json_dir=str(tmp_path))
    monkeypatch.setattr(repo, "_get_connection", lambda: None)
    scan_uuid = repo.save_scan("text_similarity", 0.5, _files_meta(), _result(), _uuid())
    repo.save_texts(scan_uuid, {"a.txt": {"raw": "x", "language": "text"}}, 8)

    scans = repo.list_scans()
    assert len(scans) == 1  # the texts sidecar is not listed as a scan
    assert scans[0]["scan_uuid"] == scan_uuid
    assert scans[0]["file_names"] == ["a.txt", "b.txt", "c.txt"]
    assert scans[0]["max_score"] == pytest.approx(0.9)
    assert scans[0]["flagged_count"] == 1
    assert scans[0]["mode"] == "text_similarity"


def test_delete_scan_removes_record_and_texts(tmp_path, monkeypatch):
    repo = ScanRepository(json_dir=str(tmp_path))
    monkeypatch.setattr(repo, "_get_connection", lambda: None)
    scan_uuid = repo.save_scan("text_similarity", 0.5, _files_meta(), _result(), _uuid())
    repo.save_texts(scan_uuid, {}, 8)

    assert repo.delete_scan(scan_uuid) is True
    assert repo.get_scan(scan_uuid) is None
    assert repo.load_texts(scan_uuid) is None
    assert repo.delete_scan(scan_uuid) is False
    assert repo.delete_scan("../../etc/passwd") is False


def test_purge_expired_removes_old_files_only(tmp_path, monkeypatch):
    import os
    import time

    repo = ScanRepository(json_dir=str(tmp_path))
    monkeypatch.setattr(repo, "_get_connection", lambda: None)
    old = repo.save_scan("text_similarity", 0.5, _files_meta(), _result(), _uuid())
    new = repo.save_scan("text_similarity", 0.5, _files_meta(), _result(), _uuid())
    stale = time.time() - 100 * 86_400
    os.utime(repo._json_path(old), (stale, stale))

    assert repo.purge_expired(days=90) == 1
    assert repo.get_scan(old) is None
    assert repo.get_scan(new) is not None


def test_retention_days_env_is_validated(tmp_path, monkeypatch):
    repo = ScanRepository(json_dir=str(tmp_path))
    monkeypatch.setattr(repo, "_get_connection", lambda: None)
    monkeypatch.setenv("RETENTION_DAYS", "soon")
    assert repo.purge_expired() == 0


def test_load_json_rejects_non_uuid_ids(tmp_path, monkeypatch):
    repo = ScanRepository(json_dir=str(tmp_path))
    monkeypatch.setattr(repo, "_get_connection", lambda: None)
    (tmp_path / "secret.json").write_text('{"scan_uuid": "secret"}', encoding="utf-8")
    assert repo.get_scan("secret") is None
    assert repo.get_scan(r"..\secret") is None


def test_storage_backend_reports_json_when_db_down(tmp_path, monkeypatch):
    repo = ScanRepository(json_dir=str(tmp_path))
    monkeypatch.setattr(repo, "_get_connection", lambda: None)
    assert repo.storage_backend() == "json"


def test_storage_backend_probe_is_cached(monkeypatch):
    repo = ScanRepository()
    calls = []

    def connect():
        calls.append(1)
        return MagicMock()

    monkeypatch.setattr(repo, "_get_connection", connect)
    assert repo.storage_backend() == "postgres"
    assert repo.storage_backend() == "postgres"
    assert len(calls) == 1


def test_list_db_maps_rows(monkeypatch, tmp_path):
    repo = ScanRepository(json_dir=str(tmp_path))
    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = [
        ("0f0e0d0c-0000-4000-8000-000000000001", datetime(2026, 1, 1), 0.7,
         ["a.txt", "b.txt"], 0.91, 1, "code_similarity"),
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    monkeypatch.setattr(repo, "_get_connection", lambda: fake_conn)

    scans = repo.list_scans()
    assert scans == [{
        "scan_uuid": "0f0e0d0c-0000-4000-8000-000000000001",
        "timestamp": "2026-01-01T00:00:00",
        "mode": "code_similarity",
        "threshold": 0.7,
        "file_names": ["a.txt", "b.txt"],
        "max_score": 0.91,
        "flagged_count": 1,
    }]


def test_db_delete_reports_rowcount(monkeypatch, tmp_path):
    repo = ScanRepository(json_dir=str(tmp_path))
    fake_cursor = MagicMock()
    fake_cursor.rowcount = 1
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    monkeypatch.setattr(repo, "_get_connection", lambda: fake_conn)
    assert repo.delete_scan(_uuid()) is True
    fake_conn.commit.assert_called_once()
