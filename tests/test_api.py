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


def test_algorithms_lists_all_five(client):
    resp = client.get("/api/algorithms")
    assert resp.status_code == 200
    assert resp.get_json()["algorithms"] == ["all", "ast", "cosine", "jaccard", "winnowing"]


def test_check_happy_path(client):
    data = {
        "algorithm": "jaccard",
        "threshold": "0.1",
        "files": [
            _upload("a.txt", "the quick brown fox jumps over the lazy dog"),
            _upload("b.txt", "the quick brown fox jumps over the lazy dog"),
        ],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()

    assert resp.status_code == 200
    assert body["algorithm"] == "jaccard"
    assert len(body["pairs"]) == 1
    assert body["pairs"][0]["score"] == pytest.approx(1.0)
    assert body["matrix"]["names"] == ["a.txt", "b.txt"]
    assert body["errors"] == []


def test_check_no_files_rejected(client):
    resp = client.post("/api/check", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "no_files"


def test_check_invalid_algorithm_rejected(client):
    data = {
        "algorithm": "bogus",
        "files": [_upload("a.txt", "hello"), _upload("b.txt", "world")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_algorithm"


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


def test_report_roundtrip(client):
    data = {
        "algorithm": "jaccard",
        "threshold": "0.1",
        "files": [_upload("a.txt", "alpha beta gamma"), _upload("b.txt", "alpha beta gamma")],
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
        "algorithm": "jaccard",
        "threshold": "0.1",
        "files": [
            _upload("a.txt", "the quick brown fox jumps over the lazy dog"),
            _upload("b.txt", "the quick brown fox jumps over the lazy dog"),
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
        "algorithm": "jaccard",
        "threshold": "0.1",
        "files": [_upload("a.txt", "alpha beta gamma"), _upload("b.txt", "alpha beta gamma")],
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
