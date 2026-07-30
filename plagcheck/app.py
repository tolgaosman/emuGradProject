""" app.py — Flask REST API. """
import json
import os
import tempfile
import uuid

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from src.audit import AuditLogger
from src.engine import AlgorithmEngine
from src.loader import MAX_BYTES, MAX_FILES, FileLoader, FileLoadError
from src.matrix import ComparisonMatrix
from src.preprocessor import Preprocessor
from src.reporter import ReportGenerator, matched_spans
from src.repository import ScanRepository
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
# 50 files * 10 MB/file, plus headroom for multipart form overhead.
app.config["MAX_CONTENT_LENGTH"] = MAX_FILES * MAX_BYTES + (1 * 1024 * 1024)
CORS(app, resources={r"/api/*": {"origins": os.environ.get("CORS_ORIGIN", "http://localhost:5173")}})

audit = AuditLogger()
repository = ScanRepository()

VALID_ALGORITHMS = {"cosine", "winnowing", "jaccard", "ast", "all"}

_TEXT_STORE_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "scans")


def _error(message: str, code: str, status: int, **extra):
    return jsonify({"error": message, "code": code, **extra}), status


def _raw_texts_path(scan_uuid: str) -> str:
    return os.path.join(_TEXT_STORE_DIR, f"{scan_uuid}_texts.json")


def _save_raw_texts(scan_uuid: str, file_data: dict) -> None:
    """Persist raw source text per scan, for the pair-comparison endpoint.

    Raw text isn't part of the relational schema (it's working data, not a
    durable record), so it's kept in its own JSON sidecar alongside the
    ScanRepository JSON fallback rather than in `scan_file`.
    """
    os.makedirs(_TEXT_STORE_DIR, exist_ok=True)
    payload = {
        name: {"raw": d["raw"], "is_python": d["is_python"]} for name, d in file_data.items()
    }
    with open(_raw_texts_path(scan_uuid), "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _load_raw_texts(scan_uuid: str) -> dict | None:
    path = _raw_texts_path(scan_uuid)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.route("/api/status", methods=["GET"])
def api_status():
    """Liveness check."""
    return jsonify({"status": "ok", "service": "plagcheck", "version": "2.0.0"})


@app.route("/api/algorithms", methods=["GET"])
def api_algorithms():
    """List the available similarity algorithms."""
    return jsonify({"algorithms": sorted(VALID_ALGORITHMS)})


@app.route("/api/check", methods=["POST"])
def api_check():
    """Run a scan over uploaded files (multipart/form-data).

    Files are validated and staged in a temporary sandbox directory that is
    always deleted afterward — the API never accepts server-side file paths,
    since a browser can't send them and doing so would be a file-read
    vulnerability.
    """
    uploads = request.files.getlist("files")
    algorithm = request.form.get(
        "algorithm", os.environ.get("DEFAULT_ALGORITHM", "cosine")
    ).lower()

    try:
        threshold = float(
            request.form.get("threshold", os.environ.get("DEFAULT_THRESHOLD", "0.70"))
        )
    except (ValueError, TypeError):
        return _error("threshold must be a number.", "invalid_threshold", 400)

    if not uploads:
        audit.log("API_ERROR", payload={"error": "No files uploaded"})
        return _error("Please upload at least 2 files.", "no_files", 400)

    if len(uploads) > MAX_FILES:
        return _error(
            f"Batch of {len(uploads)} exceeds max of {MAX_FILES} files.", "too_many_files", 400
        )

    if algorithm not in VALID_ALGORITHMS:
        return _error(
            f"Invalid algorithm '{algorithm}'.",
            "invalid_algorithm",
            400,
            choices=sorted(VALID_ALGORITHMS),
        )

    if not (0.0 < threshold < 1.0):
        return _error("threshold must be between 0 and 1.", "invalid_threshold", 400)

    scan_uuid = str(uuid.uuid4())
    audit.log(
        "SCAN_START",
        scan_uuid=scan_uuid,
        payload={"file_count": len(uploads), "algorithm": algorithm},
    )

    loader = FileLoader()
    preprocessor = Preprocessor()
    file_data: dict = {}
    files_meta: list[dict] = []
    errors: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="plagcheck_") as sandbox:
        for upload in uploads:
            safe_name = secure_filename(upload.filename or "")
            if not safe_name:
                errors.append({"file": upload.filename, "error": "Unsafe or missing filename"})
                continue

            path = os.path.join(sandbox, safe_name)
            upload.save(path)
            try:
                raw_text = loader.load(path)
                is_python = safe_name.lower().endswith(".py")
                tokens, kgrams = preprocessor.process(raw_text, is_python=is_python)
                file_data[safe_name] = {
                    "raw": raw_text,
                    "tokens": tokens,
                    "kgrams": kgrams,
                    "is_python": is_python,
                }
                files_meta.append({
                    "file_name": safe_name,
                    "file_size_bytes": os.path.getsize(path),
                    "file_format": os.path.splitext(safe_name)[1].lstrip(".").lower(),
                })
            except FileLoadError as e:
                errors.append({"file": safe_name, "error": str(e)})
                audit.log(
                    "FILE_REJECTED",
                    scan_uuid=scan_uuid,
                    payload={"file": safe_name, "error": str(e)},
                )

    if len(file_data) < 2:
        return _error(
            "Need at least 2 valid files to compare.",
            "insufficient_files",
            400,
            scan_id=scan_uuid,
            file_errors=errors,
        )

    engine = AlgorithmEngine(algorithm=algorithm)
    matrix = engine.compute(file_data)

    repository.save_scan(algorithm, threshold, files_meta, matrix, scan_uuid)
    _save_raw_texts(scan_uuid, file_data)

    pairs = [{**p, "flagged": p["score"] >= threshold} for p in matrix.all_pairs()]
    audit.log(
        "SCAN_COMPLETE",
        scan_uuid=scan_uuid,
        payload={"flagged_count": sum(1 for p in pairs if p["flagged"])},
    )

    return jsonify({
        "scan_id": scan_uuid,
        "algorithm": algorithm,
        "threshold": threshold,
        "matrix": {"names": matrix.names, "scores": matrix.as_numpy().tolist()},
        "pairs": pairs,
        "errors": errors,
    })


@app.route("/api/report/<scan_uuid>", methods=["GET"])
def api_report(scan_uuid):
    """Return a persisted scan's file list, algorithm, threshold, and pairs."""
    record = repository.get_scan(scan_uuid)
    if record is None:
        return _error("Report not found.", "not_found", 404)
    return jsonify(record)


@app.route("/api/report/<scan_uuid>/pair/<file_a>/<file_b>", methods=["GET"])
def api_report_pair(scan_uuid, file_a, file_b):
    """Return both files' raw text plus matched-span offsets for the inspector."""
    texts = _load_raw_texts(scan_uuid)
    if texts is None or file_a not in texts or file_b not in texts:
        return _error("Pair not found.", "not_found", 404)

    preprocessor = Preprocessor()
    spans_a, spans_b = matched_spans(
        texts[file_a]["raw"],
        texts[file_b]["raw"],
        texts[file_a]["is_python"],
        texts[file_b]["is_python"],
        preprocessor,
    )
    return jsonify({
        "file_a": {"name": file_a, "text": texts[file_a]["raw"], "matched_spans": spans_a},
        "file_b": {"name": file_b, "text": texts[file_b]["raw"], "matched_spans": spans_b},
    })


@app.route("/api/report/<scan_uuid>/heatmap.png", methods=["GET"])
def api_report_heatmap(scan_uuid):
    """Stream the 300 DPI similarity heatmap for a persisted scan."""
    record = repository.get_scan(scan_uuid)
    if record is None:
        return _error("Report not found.", "not_found", 404)

    names = [f["file_name"] for f in record["files"]]
    matrix = ComparisonMatrix(names)
    index = {name: i for i, name in enumerate(names)}
    for pair in record["pairs"]:
        matrix.set(index[pair["file_a"]], index[pair["file_b"]], pair["score"])

    png_bytes = ReportGenerator().heatmap_png_bytes(matrix, record["threshold"])
    return Response(png_bytes, mimetype="image/png")


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("APP_PORT", "5000")))
