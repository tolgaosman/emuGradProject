""" test_api.py — Flask REST API (multipart upload, report retrieval). """
import io

import app as app_module
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A Flask test client with the DB forced unreachable and JSON storage
    redirected into a temp dir, so tests never touch a real database or the
    repo's own output/ directory."""
    monkeypatch.setattr(app_module.repository, "_get_connection", lambda: None)
    monkeypatch.setattr(app_module.repository, "json_dir", str(tmp_path / "scans"))
    monkeypatch.setattr(app_module, "_TEXT_STORE_DIR", str(tmp_path / "texts"))
    monkeypatch.setattr(app_module.audit, "_get_connection", lambda: None)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _upload(name: str, content: str):
    return (io.BytesIO(content.encode("utf-8")), name)


def test_status_ok(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_modes_lists_both(client):
    resp = client.get("/api/modes")
    assert resp.status_code == 200
    assert resp.get_json()["modes"] == ["code_similarity", "text_similarity"]


def test_check_happy_path(client):
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "files": [
            _upload("a.txt", "the quick brown fox jumps over the lazy dog " * 20),
            _upload("b.txt", "the quick brown fox jumps over the lazy dog " * 20),
        ],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()

    assert resp.status_code == 200
    assert body["mode"] == "text_similarity"
    assert len(body["pairs"]) == 1
    # Scores are matched-span coverage, so identical documents land just
    # under 1.0: characters before the first surviving token and after the
    # last (here the leading stopword "the ") fall outside every span.
    assert body["pairs"][0]["score"] == pytest.approx(1.0, abs=0.01)
    assert body["matrix"]["names"] == ["a.txt", "b.txt"]
    assert body["errors"] == []


def test_check_no_files_rejected(client):
    resp = client.post("/api/check", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "no_files"


def test_check_invalid_mode_rejected(client):
    data = {
        "mode": "bogus",
        "files": [_upload("a.txt", "hello"), _upload("b.txt", "world")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_mode"


def test_check_non_numeric_threshold_rejected(client):
    data = {
        "threshold": "not-a-number",
        "files": [_upload("a.txt", "hello"), _upload("b.txt", "world")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_threshold"


def test_check_out_of_range_threshold_rejected(client):
    data = {
        "threshold": "1.5",
        "files": [_upload("a.txt", "hello"), _upload("b.txt", "world")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_threshold"


def test_check_too_many_files_rejected(client, monkeypatch):
    monkeypatch.setattr(app_module, "MAX_FILES", 2)
    data = {"files": [_upload(f"f{i}.txt", "content") for i in range(3)]}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "too_many_files"


def test_check_insufficient_valid_files_rejected(client):
    data = {"files": [_upload("a.exe", "not supported")]}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 400
    assert body["code"] == "insufficient_files"
    assert body["file_errors"]


def test_check_single_file_accepted(client):
    """A single valid file is a valid scan — it just has no pairs."""
    data = {"mode": "text_similarity", "files": [_upload("a.txt", "a lone document")]}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["matrix"]["names"] == ["a.txt"]
    assert body["pairs"] == []


def test_check_duplicate_filenames_do_not_collapse(client):
    """Two uploads sharing an original filename (e.g. the same file placed
    in both the reference and candidate slots) must not overwrite each
    other on disk or in file_data — both must survive as distinct entries."""
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "files": [
            _upload("dup.txt", "the quick brown fox jumps over the lazy dog " * 20),
            _upload("dup.txt", "the quick brown fox jumps over the lazy dog " * 20),
        ],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert len(body["matrix"]["names"]) == 2
    assert body["matrix"]["names"][0] == "dup.txt"
    assert body["matrix"]["names"][1] == "dup (2).txt"
    assert len(body["pairs"]) == 1
    assert body["pairs"][0]["score"] == pytest.approx(1.0, abs=0.01)


def test_check_preserves_non_ascii_filename(client):
    """The display name (used for matrix names/matching) must match the
    original filename exactly, including non-ASCII characters — the
    frontend matches a reference file by comparing this name against the
    browser's untouched File.name, so any transliteration (e.g. werkzeug's
    secure_filename turning Turkish 'İ' into 'I') would desync the two."""
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "files": [
            _upload("İzin Talebi.txt", "the quick brown fox jumps over the lazy dog " * 20),
            _upload("b.txt", "the quick brown fox jumps over the lazy dog " * 20),
        ],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert "İzin Talebi.txt" in body["matrix"]["names"]


def test_report_roundtrip(client):
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "files": [
            _upload("a.txt", "alpha beta gamma " * 20),
            _upload("b.txt", "alpha beta gamma " * 20),
        ],
    }
    check_resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    scan_id = check_resp.get_json()["scan_id"]

    resp = client.get(f"/api/report/{scan_id}")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["scan_uuid"] == scan_id
    assert len(body["files"]) == 2


def test_report_not_found(client):
    resp = client.get("/api/report/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "not_found"


def test_report_pair_returns_matched_spans(client):
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "files": [
            _upload("a.txt", "the quick brown fox jumps over the lazy dog " * 20),
            _upload("b.txt", "the quick brown fox jumps over the lazy dog " * 20),
        ],
    }
    check_resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    scan_id = check_resp.get_json()["scan_id"]

    resp = client.get(f"/api/report/{scan_id}/pair/a.txt/b.txt")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["file_a"]["matched_spans"]
    assert body["file_b"]["matched_spans"]


def test_report_pair_not_found(client):
    resp = client.get("/api/report/00000000-0000-0000-0000-000000000000/pair/a.txt/b.txt")
    assert resp.status_code == 404


def test_report_heatmap_streams_png(client):
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "files": [
            _upload("a.txt", "alpha beta gamma " * 20),
            _upload("b.txt", "alpha beta gamma " * 20),
        ],
    }
    check_resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    scan_id = check_resp.get_json()["scan_id"]

    resp = client.get(f"/api/report/{scan_id}/heatmap.png")
    assert resp.status_code == 200
    assert resp.content_type == "image/png"
    assert len(resp.data) > 0


def test_report_heatmap_not_found(client):
    resp = client.get("/api/report/00000000-0000-0000-0000-000000000000/heatmap.png")
    assert resp.status_code == 404


def test_check_rejects_wrong_extension_for_mode(client):
    """A .py file is rejected by text_similarity even though .py is a
    generally supported extension — it's not on that mode's allow-list. The
    other file is still valid, so the scan succeeds with just that one."""
    data = {
        "mode": "text_similarity",
        "files": [_upload("a.py", "print(1)"), _upload("b.txt", "hello world")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert any(".py" in e["error"] for e in body["errors"])
    assert body["matrix"]["names"] == ["b.txt"]


def test_check_rejects_wrong_extension_for_code_mode(client):
    data = {
        "mode": "code_similarity",
        "files": [_upload("a.docx", "hello"), _upload("b.py", "print(1)")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert any(".docx" in e["error"] for e in body["errors"])
    assert body["matrix"]["names"] == ["b.py"]


def test_check_rejects_wrong_extension_for_all_files(client):
    """When every uploaded file fails the mode's extension check, that's the
    genuine insufficient_files case — 0 valid files, not 1."""
    data = {
        "mode": "text_similarity",
        "files": [_upload("a.py", "print(1)"), _upload("b.py", "print(2)")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 400
    assert body["code"] == "insufficient_files"


def test_detect_language_java(client):
    java = "public class Main { public static void main(String[] a) { System.out.println(1); } }"
    resp = client.post("/api/detect-language", json={"text": java})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["language"] == "java"
    assert 0.0 <= body["confidence"] <= 1.0


def test_detect_language_rejects_empty(client):
    resp = client.post("/api/detect-language", json={"text": "   "})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "empty_text"


def test_detect_language_rejects_too_long(client):
    resp = client.post("/api/detect-language", json={"text": "x" * 15_001})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "text_too_long"


def test_check_similarity_index_in_response(client):
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "files": [
            _upload("a.txt", "the quick brown fox jumps over the lazy dog near the water " * 3),
            _upload("b.txt", "the quick brown fox jumps over the lazy dog near the water " * 3),
        ],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["similarity_indices"]["a.txt"] > 0.0
    assert body["source_breakdowns"]["a.txt"][0]["source"] == "b.txt"


def test_algorithms_lists_choices_per_mode(client):
    resp = client.get("/api/algorithms")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["by_mode"]["text_similarity"] == ["auto", "cosine", "winnowing", "jaccard"]
    assert body["by_mode"]["code_similarity"] == ["auto", "ast", "winnowing", "jaccard"]
    assert "cosine" in body["algorithms"]


def test_check_defaults_to_auto_algorithm_and_echoes_it(client):
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "files": [_upload("a.txt", "hello world " * 10), _upload("b.txt", "hello world " * 10)],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.get_json()["algorithm"] == "auto"


def test_check_accepts_forced_algorithm(client):
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "algorithm": "cosine",
        "files": [_upload("a.txt", "hello world " * 10), _upload("b.txt", "hello world " * 10)],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["algorithm"] == "cosine"


def test_check_rejects_algorithm_not_valid_for_mode(client):
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "algorithm": "ast",
        "files": [_upload("a.txt", "hello world"), _upload("b.txt", "hello world")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_algorithm"
