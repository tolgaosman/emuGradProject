""" test_api.py — Flask REST API (multipart upload, report retrieval). """
import io

import app as app_module
import pytest
from src.websearch import SearchResult


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A Flask test client with the DB forced unreachable and JSON storage
    redirected into a temp dir, so tests never touch a real database or the
    repo's own output/ directory."""
    monkeypatch.setattr(app_module.repository, "_get_connection", lambda: None)
    monkeypatch.setattr(app_module.repository, "json_dir", str(tmp_path / "scans"))
    monkeypatch.setattr(app_module, "_TEXT_STORE_DIR", str(tmp_path / "texts"))
    monkeypatch.setattr(app_module.audit, "_get_connection", lambda: None)
    # Web search is unconfigured by default in tests, regardless of what's in
    # the developer's .env — tests that need it set fake credentials
    # themselves alongside a mocked WebSearchClient.
    monkeypatch.delenv("WEB_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("WEB_SEARCH_ENGINE_ID", raising=False)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


class _FakeWebClient:
    """Test double for WebSearchClient — no network calls."""

    def __init__(self, *args, **kwargs):
        pass

    def search(self, query, max_results=5):
        return [SearchResult(url="https://example.com/hit", title="Hit", snippet="")]

    def fetch_page_text(self, url, max_bytes=2_000_000):
        return "the quick brown fox jumps over the lazy dog near the water today"


def _upload(name: str, content: str):
    return (io.BytesIO(content.encode("utf-8")), name)


def test_status_ok(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_modes_lists_all_four(client):
    resp = client.get("/api/modes")
    assert resp.status_code == 200
    assert resp.get_json()["modes"] == ["ai_code", "ai_text", "code_similarity", "text_similarity"]


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
    assert body["pairs"][0]["score"] == pytest.approx(1.0)
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
    generally supported extension — it's not on that mode's allow-list."""
    data = {
        "mode": "text_similarity",
        "files": [_upload("a.py", "print(1)"), _upload("b.txt", "hello world")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 400
    assert any(".py" in e["error"] for e in body["file_errors"])


def test_check_rejects_wrong_extension_for_code_mode(client):
    data = {
        "mode": "code_similarity",
        "files": [_upload("a.docx", "hello"), _upload("b.py", "print(1)")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 400
    assert any(".docx" in e["error"] for e in body["file_errors"])


def test_check_ai_text_mode_accepts_single_file(client):
    """AI modes only need 1 file, unlike the 2-file minimum for similarity modes."""
    data = {"mode": "ai_text", "files": [_upload("a.txt", "A short passage of ordinary prose.")]}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["matrix"] is None
    assert len(body["ai_scores"]) == 1
    assert body["ai_scores"][0]["file"] == "a.txt"
    assert body["ai_scores"][0]["band"] in ("low", "possible", "likely")
    assert "signals" in body["ai_scores"][0]
    assert "segments" in body["ai_scores"][0]


def test_check_ai_code_mode_java(client):
    java = (
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        System.out.println(1);\n"
        "    }\n"
        "}\n"
    )
    data = {"mode": "ai_code", "files": [_upload("Main.java", java)]}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["ai_scores"][0]["file"] == "Main.java"


def test_heatmap_not_available_for_ai_scan(client):
    data = {"mode": "ai_text", "files": [_upload("a.txt", "Some plain text content here.")]}
    check_resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    scan_id = check_resp.get_json()["scan_id"]

    resp = client.get(f"/api/report/{scan_id}/heatmap.png")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "not_applicable"


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
    assert body["by_mode"]["ai_text"] == []
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


def test_check_rejects_algorithm_for_ai_mode(client):
    data = {
        "mode": "ai_text",
        "algorithm": "cosine",
        "files": [_upload("a.txt", "hello world, this is a short essay about foxes.")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_algorithm"


# -- web-source comparison ---------------------------------------------------


def test_check_include_web_default_no_credentials_degrades_not_fails(client):
    """include_web defaults to true, but with no server credentials the scan
    still completes — it just falls back to offline comparison instead of a
    hard error, since a normal file-vs-file scan shouldn't fail because
    nobody configured a search API key."""
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "files": [_upload("a.txt", "hello world " * 10), _upload("b.txt", "hello world " * 10)],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["web_search_unavailable"] is True
    assert body["web_matches"] == {}


def test_check_explicit_include_web_no_credentials_is_hard_error(client):
    """Explicitly asking for include_web=true when the server has no
    credentials is a client-visible error, unlike the silent default-true
    fallback above — the client asked for something the server can't do."""
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "include_web": "true",
        "files": [_upload("a.txt", "hello world " * 10), _upload("b.txt", "hello world " * 10)],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "web_search_unavailable"


def test_check_include_web_false_skips_even_with_credentials(client, monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "fake-key")
    monkeypatch.setenv("WEB_SEARCH_ENGINE_ID", "fake-cx")
    monkeypatch.setattr(app_module, "WebSearchClient", _FakeWebClient)
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "include_web": "false",
        "files": [_upload("a.txt", "hello world " * 10), _upload("b.txt", "hello world " * 10)],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["web_search_unavailable"] is False
    assert body["web_matches"] == {}


def test_check_web_enabled_single_file_accepted_and_populates_web_matches(client, monkeypatch):
    """With credentials configured (mocked, no real network), a single
    uploaded file is now enough for a similarity-mode scan — the internet
    stands in for the second file."""
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "fake-key")
    monkeypatch.setenv("WEB_SEARCH_ENGINE_ID", "fake-cx")
    monkeypatch.setattr(app_module, "WebSearchClient", _FakeWebClient)
    data = {
        "mode": "text_similarity",
        "threshold": "0.1",
        "files": [
            _upload(
                "a.txt",
                "The quick brown fox jumps over the lazy dog near the water today, "
                "a distinctive sentence used for testing purposes here.",
            )
        ],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["web_search_unavailable"] is False
    assert body["web_matches"]["a.txt"]
    assert body["web_matches"]["a.txt"][0]["url"] == "https://example.com/hit"


def test_check_web_ineligible_mode_ignores_include_web(client, monkeypatch):
    """ai_text is never web-eligible; include_web is simply irrelevant there,
    not an error, and doesn't relax that mode's own 1-file minimum further."""
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "fake-key")
    monkeypatch.setenv("WEB_SEARCH_ENGINE_ID", "fake-cx")
    monkeypatch.setattr(app_module, "WebSearchClient", _FakeWebClient)
    data = {
        "mode": "ai_text",
        "files": [_upload("a.txt", "A short passage of ordinary prose about nothing much.")],
    }
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["web_matches"] == {}
