""" test_api_reports.py — history, exports, rehydration and API hardening. """
import io
import json
import os

import pytest
from docx import Document

import app as app_module

PROSE = "the quick brown fox jumps over the lazy dog near the quiet river bank " * 12


def _upload(name: str, content: str | bytes):
    data = content.encode("utf-8") if isinstance(content, str) else content
    return (io.BytesIO(data), name)


def _scan(client, *files, **form) -> dict:
    data = {"mode": "text_similarity", "threshold": "0.1", **form, "files": list(files)}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _docx_bytes(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, cell in enumerate(row):
                grid.cell(r, c).text = cell
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def test_check_reports_summary_duration_and_file_info(client):
    body = _scan(client, _upload("a.txt", PROSE), _upload("b.txt", PROSE))

    assert body["duration_s"] >= 0
    assert body["summary"]["pair_count"] == 1
    assert body["summary"]["flagged_count"] == 1
    assert body["summary"]["max_score"] == pytest.approx(body["pairs"][0]["score"])
    assert [f["name"] for f in body["files"]] == ["a.txt", "b.txt"]
    assert [f["index"] for f in body["files"]] == [0, 1]
    assert body["files"][0]["word_count"] > 100
    assert body["flagged"] == [p for p in body["pairs"] if p["flagged"]]


def test_check_pairs_carry_matched_kgram_count(client):
    body = _scan(client, _upload("a.txt", PROSE), _upload("b.txt", PROSE))
    assert body["pairs"][0]["matched_kgrams"] > 0


def test_check_file_indices_skip_rejected_uploads(client):
    body = _scan(client, _upload("bad.py", "x = 1"), _upload("a.txt", PROSE))
    assert [(f["name"], f["index"]) for f in body["files"]] == [("a.txt", 1)]


def test_threshold_bounds_follow_the_report(client):
    for value, ok in (("0.01", True), ("0.99", True), ("0.005", False), ("0.995", False)):
        data = {"mode": "text_similarity", "threshold": value, "files": [_upload("a.txt", PROSE)]}
        resp = client.post("/api/check", data=data, content_type="multipart/form-data")
        assert (resp.status_code == 200) is ok, value


def test_negative_min_match_words_rejected(client):
    data = {"min_match_words": "-1", "files": [_upload("a.txt", PROSE)]}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_min_match_words"


def test_corrupt_docx_is_a_file_error_not_a_crash(client):
    body = _scan(client, _upload("broken.docx", b"PK\x03\x04 not really a zip"),
                 _upload("a.txt", PROSE))
    assert [e["file"] for e in body["errors"]] == ["broken.docx"]


def test_file_errors_never_expose_sandbox_paths(client):
    body = _scan(client, _upload("empty.txt", ""), _upload("a.txt", PROSE))
    message = body["errors"][0]["error"]
    assert "empty.txt" in message
    assert "upload_" not in message
    assert "plagcheck_" not in message


def test_docx_table_text_is_extracted(client):
    docx = _docx_bytes(["Heading"], [[PROSE[:200], PROSE[200:400]]])
    body = _scan(client, _upload("t.docx", docx), _upload("a.txt", PROSE))
    assert body["files"][0]["word_count"] > 50


def test_control_characters_are_stripped_from_names(client):
    body = _scan(client, _upload("re‮port.txt", PROSE), _upload("b.txt", PROSE))
    assert body["files"][0]["name"] == "report.txt"


def test_overlong_names_are_truncated_keeping_the_extension(client):
    body = _scan(client, _upload("x" * 400 + ".txt", PROSE), _upload("b.txt", PROSE))
    name = body["files"][0]["name"]
    assert len(name) == app_module.MAX_NAME_LENGTH
    assert name.endswith(".txt")


def test_audit_records_file_names_mode_and_scores(client, tmp_path):
    _scan(client, _upload("a.txt", PROSE), _upload("b.txt", PROSE))
    log = (tmp_path / "audit.log").read_text(encoding="utf-8")
    complete = next(line for line in log.splitlines() if "SCAN_COMPLETE" in line)
    payload = json.loads(complete.split("Payload: ", 1)[1].split(" | Error:", 1)[0])
    assert payload["files"] == ["a.txt", "b.txt"]
    assert payload["mode"] == "text_similarity"
    assert payload["max_score"] > 0.9


def test_rejected_request_is_audited(client, tmp_path):
    client.post("/api/check", data={"mode": "nope"}, content_type="multipart/form-data")
    assert "API_ERROR" in (tmp_path / "audit.log").read_text(encoding="utf-8")


def test_scan_failure_returns_envelope(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(app_module.ScanEngine, "compute", boom)
    data = {"files": [_upload("a.txt", PROSE)]}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert resp.status_code == 500
    assert body["code"] == "scan_failed"
    assert "exploded" not in body["error"]


# -- Error envelope --------------------------------------------------------------


def test_unknown_route_uses_json_envelope(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "not_found"


def test_wrong_method_uses_json_envelope(client):
    resp = client.get("/api/check")
    assert resp.status_code == 405
    assert resp.get_json()["code"] == "method_not_allowed"


def test_oversize_upload_uses_json_envelope(client, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "MAX_CONTENT_LENGTH", 1024)
    data = {"files": [_upload("a.txt", "x" * 4096)]}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 413
    assert resp.get_json()["code"] == "payload_too_large"


def test_unexpected_errors_hide_internals(client, monkeypatch):
    def boom(_limit):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(app_module.repository, "list_scans", boom)
    resp = client.get("/api/scans")
    assert resp.status_code == 500
    assert resp.get_json() == {
        "error": "Something went wrong on the server.",
        "code": "internal_error",
    }


@pytest.mark.parametrize("scan_id", ["not-a-uuid", "..%5C..%5Cetc", "C:%5Cwindows"])
def test_non_uuid_report_ids_are_not_found(client, scan_id):
    for suffix in ("", "/heatmap.png", "/matrix.csv", "/report.html", "/pair/a.txt/b.txt"):
        resp = client.get(f"/api/report/{scan_id}{suffix}")
        assert resp.status_code == 404, suffix
        assert resp.get_json()["code"] == "not_found"


# -- Status, history, rehydration, exports ---------------------------------------


def test_status_reports_offline_storage_and_uptime(client):
    body = client.get("/api/status").get_json()
    assert body["offline"] is True
    assert body["storage"] == "json"
    assert body["uptime_s"] >= 0
    assert body["version"] == app_module.API_VERSION


def test_scans_lists_newest_first(client):
    first = _scan(client, _upload("a.txt", PROSE), _upload("b.txt", PROSE))
    second = _scan(client, _upload("c.txt", PROSE), _upload("d.txt", "totally different words"))

    scans = client.get("/api/scans").get_json()["scans"]
    ids = [s["scan_uuid"] for s in scans]
    assert set(ids) == {first["scan_id"], second["scan_id"]}
    entry = next(s for s in scans if s["scan_uuid"] == first["scan_id"])
    assert entry["file_names"] == ["a.txt", "b.txt"]
    assert entry["mode"] == "text_similarity"
    assert entry["flagged_count"] == 1


def test_scans_rejects_non_numeric_limit(client):
    resp = client.get("/api/scans?limit=many")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_limit"


def test_report_rehydrates_the_check_response(client):
    body = _scan(client, _upload("a.txt", PROSE), _upload("b.txt", PROSE), min_match_words="5")
    report = client.get(f"/api/report/{body['scan_id']}").get_json()

    assert report["scan_id"] == body["scan_id"]
    assert report["mode"] == "text_similarity"
    assert report["min_match_words"] == 5
    assert report["matrix"]["names"] == body["matrix"]["names"]
    for got, want in zip(report["matrix"]["scores"], body["matrix"]["scores"], strict=True):
        assert got == pytest.approx(want)
    assert report["similarity_indices"] == pytest.approx(body["similarity_indices"])
    assert report["pairs"][0]["matched_kgrams"] == body["pairs"][0]["matched_kgrams"]
    assert report["comparison_available"] is True


def test_delete_removes_report_and_comparison_text(client):
    body = _scan(client, _upload("a.txt", PROSE), _upload("b.txt", PROSE))
    scan_id = body["scan_id"]

    assert client.delete(f"/api/report/{scan_id}").status_code == 204
    assert client.get(f"/api/report/{scan_id}").status_code == 404
    assert client.get(f"/api/report/{scan_id}/pair/a.txt/b.txt").status_code == 404
    assert client.delete(f"/api/report/{scan_id}").status_code == 404


def test_pair_reports_matched_kgrams_and_min_match_words(client):
    body = _scan(client, _upload("a.txt", PROSE), _upload("b.txt", PROSE))
    pair = client.get(f"/api/report/{body['scan_id']}/pair/a.txt/b.txt").get_json()
    assert pair["matched_kgrams"] == body["pairs"][0]["matched_kgrams"]
    assert pair["min_match_words"] == body["min_match_words"]


def test_matrix_csv_download(client):
    body = _scan(client, _upload("a.txt", PROSE), _upload("b.txt", PROSE))
    resp = client.get(f"/api/report/{body['scan_id']}/matrix.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert resp.get_data(as_text=True).splitlines()[0] == ",a.txt,b.txt"


def test_html_report_download_highlights_flagged_pairs(client):
    body = _scan(client, _upload("a.txt", PROSE), _upload("b.txt", PROSE))
    resp = client.get(f"/api/report/{body['scan_id']}/report.html")
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"
    assert "Flagged for review" in page
    assert "matched 5-grams" in page
    assert "<mark>" in page


def test_html_report_without_stored_text_falls_back_to_table(client):
    body = _scan(client, _upload("a.txt", PROSE), _upload("b.txt", PROSE))
    os.remove(app_module.repository._texts_path(body["scan_id"]))
    page = client.get(f"/api/report/{body['scan_id']}/report.html").get_data(as_text=True)
    assert "Flagged for review" in page
    assert "<mark>" not in page


def test_full_matrix_heatmap_for_batch(client):
    body = _scan(
        client, _upload("a.txt", PROSE), _upload("b.txt", PROSE), _upload("c.txt", PROSE)
    )
    resp = client.get(f"/api/report/{body['scan_id']}/heatmap.png?ref=all")
    assert resp.status_code == 200
    assert resp.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_heatmap_tolerates_mathtext_in_names(client):
    body = _scan(client, _upload("$x^2$.txt", PROSE), _upload("b.txt", PROSE))
    resp = client.get(f"/api/report/{body['scan_id']}/heatmap.png?ref=all")
    assert resp.status_code == 200
