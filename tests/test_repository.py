""" test_repository.py — ScanRepository persistence and JSON fallback. """
from datetime import datetime
from unittest.mock import MagicMock

from src.engine import ScanEngine, ScanResult
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


def _ai_result() -> ScanResult:
    """A real AI-mode ScanResult, via the engine, so AIAssessment stays in sync."""
    raw = "Some ordinary sample prose for AI checking."
    file_data = {"a.txt": {"raw": raw, "language": "text"}}
    return ScanEngine(mode="ai_text").compute(file_data)


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


def test_json_fallback_round_trip_ai_mode(tmp_path, monkeypatch):
    """AI-mode results (no matrix) round-trip through JSON too."""
    repo = ScanRepository(json_dir=str(tmp_path))
    monkeypatch.setattr(repo, "_get_connection", lambda: None)

    files_meta = [{"file_name": "a.txt", "file_size_bytes": 10, "file_format": "txt"}]
    scan_uuid = repo.save_scan("ai_text", 0.70, files_meta, _ai_result())
    record = repo.get_scan(scan_uuid)
    assert record is not None
    assert record["pairs"] == []
    assert len(record["ai_scores"]) == 1
    assert record["ai_scores"][0]["file"] == "a.txt"
    assert record["ai_scores"][0]["band"] in ("low", "possible", "likely")


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


def test_save_db_persists_ai_results():
    """scan_ai_result rows are written for AI-mode scans."""
    repo = ScanRepository()

    fake_cursor = MagicMock()
    fake_cursor.fetchone.side_effect = [(1,), (10,), (20,)]  # user, scan_request, one file
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor

    record = repo._build_record(
        "uuid-ai",
        "ai_text",
        0.70,
        [{"file_name": "a.txt", "file_size_bytes": 10, "file_format": "txt"}],
        _ai_result(),
    )
    repo._save_db(fake_conn, record)

    ai_calls = [c for c in fake_cursor.execute.call_args_list if "scan_ai_result" in c.args[0]]
    assert len(ai_calls) == 1
    _, params = ai_calls[0].args
    scan_id, file_id, probability, band = params
    assert scan_id == 10
    assert file_id == 20
    assert 0.0 <= probability <= 1.0
    assert band in ("low", "possible", "likely")


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
        [],  # scan_ai_result rows
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
    assert record["ai_scores"] == []
    fake_conn.close.assert_called_once()


def test_load_db_reconstructs_ai_results(monkeypatch):
    """get_scan() rebuilds AI scores from scan_ai_result rows."""
    repo = ScanRepository()

    fake_cursor = MagicMock()
    fake_cursor.fetchone.side_effect = [
        (10, 0.70, "complete", datetime(2026, 1, 1, 12, 0, 0)),
    ]
    fake_cursor.fetchall.side_effect = [
        [("ai_text",)],  # scan_algorithm rows
        [(1, "a.txt", 100, "txt", None)],
        [],  # no scan_pair rows for an AI-mode scan
        [(1, 0.42, "possible")],  # scan_ai_result rows
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    monkeypatch.setattr(repo, "_get_connection", lambda: fake_conn)

    record = repo.get_scan("uuid-ai")
    assert record is not None
    assert record["ai_scores"] == [
        {"file": "a.txt", "overall_probability": 0.42, "band": "possible"}
    ]


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
        [],
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
