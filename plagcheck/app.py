""" app.py — Flask REST API. """
import json
import os
import tempfile
import uuid

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from src.audit import AuditLogger
from src.engine import ALGORITHMS_BY_MODE, WEB_ELIGIBLE_MODES, ScanEngine
from src.language import MODES, detect_language, is_allowed_for_mode, language_for_extension
from src.loader import MAX_BYTES, MAX_FILES, FileLoader, FileLoadError
from src.matrix import ComparisonMatrix
from src.preprocessor import Preprocessor
from src.reporter import ReportGenerator, matched_spans
from src.repository import ScanRepository
from src.similarity_index import DEFAULT_MIN_MATCH_WORDS
from src.websearch import WebSearchClient
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
# 50 files * 10 MB/file, plus headroom for multipart form overhead.
app.config["MAX_CONTENT_LENGTH"] = MAX_FILES * MAX_BYTES + (1 * 1024 * 1024)
CORS(app, resources={r"/api/*": {"origins": os.environ.get("CORS_ORIGIN", "http://localhost:5173")}})

audit = AuditLogger()
repository = ScanRepository()

VALID_MODES = MODES

_TEXT_STORE_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "scans")

#: Modes whose scan record has no pairwise matrix (see engine.ScanResult.is_ai).
_AI_MODES = {"ai_code", "ai_text"}

WEB_SEARCH_MAX_QUERIES_PER_SCAN = int(os.environ.get("WEB_SEARCH_MAX_QUERIES_PER_SCAN", "5"))
WEB_SEARCH_BUDGET_SECONDS = float(os.environ.get("WEB_SEARCH_BUDGET_SECONDS", "20"))


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
        name: {"raw": d["raw"], "language": d["language"]} for name, d in file_data.items()
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
    return jsonify({"status": "ok", "service": "plagcheck", "version": "3.1.0"})


@app.route("/api/modes", methods=["GET"])
def api_modes():
    """List the available scanning modes."""
    return jsonify({"modes": sorted(VALID_MODES)})


@app.route("/api/algorithms", methods=["GET"])
def api_algorithms():
    """List the algorithm choices selectable per mode.

    "auto" is each similarity mode's designed blend (see `engine.py`'s
    `_CODE_*_WEIGHT` / `_TEXT_*_WEIGHT`); the rest force a single named
    model, for demoing/reviewing each algorithm individually. AI modes have
    no algorithm choice at all.
    """
    return jsonify({
        "algorithms": sorted({a for choices in ALGORITHMS_BY_MODE.values() for a in choices}),
        "by_mode": ALGORITHMS_BY_MODE,
    })


@app.route("/api/detect-language", methods=["POST"])
def api_detect_language():
    """Guess which of python/java/c/cpp a pasted code snippet is written in.

    Used by the paste-box UI in code_similarity/ai_code modes so the right
    extension/tokenizer path is picked without asking the user up front.
    """
    body = request.get_json(silent=True) or {}
    text = body.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return _error("Please provide non-empty 'text'.", "empty_text", 400)
    if len(text) > 15_000:
        return _error("Text exceeds the 15,000 character limit.", "text_too_long", 400)

    language, confidence = detect_language(text)
    return jsonify({"language": language, "confidence": confidence})


@app.route("/api/check", methods=["POST"])
def api_check():
    """Run a scan over uploaded files (multipart/form-data).

    Files are validated and staged in a temporary sandbox directory that is
    always deleted afterward — the API never accepts server-side file paths,
    since a browser can't send them and doing so would be a file-read
    vulnerability.
    """
    uploads = request.files.getlist("files")
    mode = request.form.get(
        "mode", os.environ.get("DEFAULT_MODE", "text_similarity")
    ).lower()
    algorithm = request.form.get("algorithm", "auto").lower()

    include_web_raw = request.form.get("include_web")
    include_web_explicit = include_web_raw is not None
    include_web = (include_web_raw if include_web_explicit else "true").lower() in (
        "1",
        "true",
        "yes",
    )

    try:
        threshold = float(
            request.form.get("threshold", os.environ.get("DEFAULT_THRESHOLD", "0.70"))
        )
    except (ValueError, TypeError):
        return _error("threshold must be a number.", "invalid_threshold", 400)

    try:
        min_match_words = int(request.form.get("min_match_words", DEFAULT_MIN_MATCH_WORDS))
    except (ValueError, TypeError):
        return _error("min_match_words must be an integer.", "invalid_min_match_words", 400)

    if not uploads:
        audit.log("API_ERROR", payload={"error": "No files uploaded"})
        return _error("Please upload at least 1 file.", "no_files", 400)

    if len(uploads) > MAX_FILES:
        return _error(
            f"Batch of {len(uploads)} exceeds max of {MAX_FILES} files.", "too_many_files", 400
        )

    if mode not in VALID_MODES:
        return _error(
            f"Invalid mode '{mode}'.",
            "invalid_mode",
            400,
            choices=sorted(VALID_MODES),
        )

    mode_algorithms = ALGORITHMS_BY_MODE.get(mode, [])
    if mode_algorithms and algorithm not in mode_algorithms:
        return _error(
            f"Algorithm '{algorithm}' is not available for mode '{mode}'.",
            "invalid_algorithm",
            400,
            choices=mode_algorithms,
        )
    if not mode_algorithms and algorithm != "auto":
        return _error(
            f"Mode '{mode}' has no selectable algorithm.",
            "invalid_algorithm",
            400,
            choices=["auto"],
        )

    if not (0.0 < threshold < 1.0):
        return _error("threshold must be between 0 and 1.", "invalid_threshold", 400)

    is_ai = mode in _AI_MODES

    # Web comparison is on by default for the similarity modes (see
    # websearch.py). If it's not configured on the server: an explicit
    # `include_web=true` from the client is a hard error (the client asked
    # for something the server can't do), but relying on the default just
    # falls back to offline file-vs-file comparison — a scan shouldn't fail
    # because nobody set an API key.
    web_client = None
    web_search_unavailable = False
    if include_web and mode in WEB_ELIGIBLE_MODES:
        api_key = os.environ.get("WEB_SEARCH_API_KEY", "")
        engine_id = os.environ.get("WEB_SEARCH_ENGINE_ID", "")
        if api_key and engine_id:
            web_client = WebSearchClient(api_key=api_key, engine_id=engine_id)
        elif include_web_explicit:
            return _error(
                "Web search is not configured on this server "
                "(WEB_SEARCH_API_KEY / WEB_SEARCH_ENGINE_ID missing).",
                "web_search_unavailable",
                400,
            )
        else:
            web_search_unavailable = True
            include_web = False
    else:
        include_web = include_web and mode in WEB_ELIGIBLE_MODES

    min_files = 1 if (is_ai or web_client is not None) else 2

    scan_uuid = str(uuid.uuid4())
    audit.log(
        "SCAN_START",
        scan_uuid=scan_uuid,
        payload={"file_count": len(uploads), "mode": mode},
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

            ext = os.path.splitext(safe_name)[1].lower()
            if not is_allowed_for_mode(ext, mode):
                errors.append({
                    "file": upload.filename,
                    "error": f"Format {ext or '(none)'} is not accepted by mode '{mode}'",
                })
                continue

            path = os.path.join(sandbox, safe_name)
            upload.save(path)
            try:
                raw_text = loader.load(path, mode=mode)
                language = language_for_extension(ext) or "text"
                tokens, kgrams = preprocessor.process(raw_text, language=language)
                file_data[safe_name] = {
                    "raw": raw_text,
                    "tokens": tokens,
                    "kgrams": kgrams,
                    "language": language,
                }
                files_meta.append({
                    "file_name": safe_name,
                    "file_size_bytes": os.path.getsize(path),
                    "file_format": ext.lstrip(".").lower(),
                })
            except FileLoadError as e:
                errors.append({"file": safe_name, "error": str(e)})
                audit.log(
                    "FILE_REJECTED",
                    scan_uuid=scan_uuid,
                    payload={"file": safe_name, "error": str(e)},
                )

    if len(file_data) < min_files:
        return _error(
            f"Need at least {min_files} valid file(s) for mode '{mode}'.",
            "insufficient_files",
            400,
            scan_id=scan_uuid,
            file_errors=errors,
        )

    def _on_web_query(query: str, result_count: int) -> None:
        audit.log(
            "WEB_SEARCH_QUERY",
            scan_uuid=scan_uuid,
            payload={"query": query, "result_count": result_count},
        )

    engine = ScanEngine(mode=mode, algorithm=algorithm)
    result = engine.compute(
        file_data,
        preprocessor=preprocessor,
        min_match_words=min_match_words,
        web_client=web_client,
        max_web_queries=WEB_SEARCH_MAX_QUERIES_PER_SCAN,
        on_query=_on_web_query if web_client is not None else None,
        web_budget_seconds=WEB_SEARCH_BUDGET_SECONDS,
    )

    matrix_payload = None
    pairs_payload = []
    similarity_indices_payload = {}
    source_breakdowns_payload = {}
    web_matches_payload = {}
    ai_scores = []

    if is_ai:
        ai_scores = [
            {"file": name, **result.ai_assessments[name].to_dict()} for name in result.names
        ]
    else:
        assert result.matrix is not None  # guaranteed for non-AI modes by ScanEngine.compute
        matrix_payload = {
            "names": result.matrix.names,
            "scores": result.matrix.as_numpy().tolist(),
        }
        pairs_payload = [
            {**p, "flagged": p["score"] >= threshold} for p in result.matrix.all_pairs()
        ]
        similarity_indices_payload = result.similarity_indices
        source_breakdowns_payload = result.source_breakdowns
        web_matches_payload = {
            name: [m.to_dict() for m in matches] for name, matches in result.web_matches.items()
        }

    repository.save_scan(mode, threshold, files_meta, result, scan_uuid)
    _save_raw_texts(scan_uuid, file_data)

    audit.log(
        "SCAN_COMPLETE",
        scan_uuid=scan_uuid,
        payload={
            "flagged_count": sum(1 for p in pairs_payload if p["flagged"]),
            "ai_scored_count": len(ai_scores),
        },
    )

    return jsonify({
        "scan_id": scan_uuid,
        "mode": mode,
        "algorithm": algorithm,
        "threshold": threshold,
        "min_match_words": min_match_words,
        "matrix": matrix_payload,
        "pairs": pairs_payload,
        "similarity_indices": similarity_indices_payload,
        "source_breakdowns": source_breakdowns_payload,
        "web_matches": web_matches_payload,
        "web_search_unavailable": web_search_unavailable,
        "ai_scores": ai_scores,
        "errors": errors,
    })


@app.route("/api/report/<scan_uuid>", methods=["GET"])
def api_report(scan_uuid):
    """Return a persisted scan's file list, mode, threshold, and results."""
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
        texts[file_a]["language"],
        texts[file_b]["language"],
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
    if record["algorithm"] in _AI_MODES:
        return _error(
            "Heatmaps aren't available for AI-detection scans.", "not_applicable", 400
        )

    names = [f["file_name"] for f in record["files"]]
    matrix = ComparisonMatrix(names)
    index = {name: i for i, name in enumerate(names)}
    for pair in record["pairs"]:
        matrix.set(index[pair["file_a"]], index[pair["file_b"]], pair["score"])

    png_bytes = ReportGenerator().heatmap_png_bytes(matrix, record["threshold"])
    return Response(png_bytes, mimetype="image/png")


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("APP_PORT", "5000")))
