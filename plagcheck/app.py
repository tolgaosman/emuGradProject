""" app.py — Flask REST API. """
import json
import os
import tempfile
import uuid
from urllib.parse import quote

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from src.audit import AuditLogger
from src.engine import ALGORITHMS_BY_MODE, ScanEngine
from src.language import MODES, detect_language, is_allowed_for_mode, language_for_extension
from src.loader import MAX_BYTES, MAX_FILES, FileLoader, FileLoadError
from src.matrix import ComparisonMatrix
from src.preprocessor import Preprocessor
from src.reporter import ReportGenerator, matched_spans
from src.repository import ScanRepository
from src.similarity_index import DEFAULT_MIN_MATCH_WORDS, _filter_by_word_count

load_dotenv()

app = Flask(__name__)
# 50 files * 10 MB/file, plus headroom for multipart form overhead.
app.config["MAX_CONTENT_LENGTH"] = MAX_FILES * MAX_BYTES + (1 * 1024 * 1024)
CORS(app, resources={r"/api/*": {"origins": os.environ.get("CORS_ORIGIN", "http://localhost:5173")}})

audit = AuditLogger()
repository = ScanRepository()

VALID_MODES = MODES

_TEXT_STORE_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "scans")


def _error(message: str, code: str, status: int, **extra):
    return jsonify({"error": message, "code": code, **extra}), status


def _raw_texts_path(scan_uuid: str) -> str:
    return os.path.join(_TEXT_STORE_DIR, f"{scan_uuid}_texts.json")


def _save_raw_texts(scan_uuid: str, file_data: dict, min_match_words: int) -> None:
    """Persist raw source text per scan, for the pair-comparison endpoint.

    Raw text isn't part of the relational schema (it's working data, not a
    durable record), so it's kept in its own JSON sidecar alongside the
    ScanRepository JSON fallback rather than in `scan_file`.

    The scan's `min_match_words` rides along so the pair endpoint can filter
    spans exactly as the scan scored them — otherwise the inspector would
    highlight matches the score excluded.
    """
    os.makedirs(_TEXT_STORE_DIR, exist_ok=True)
    payload = {
        "min_match_words": min_match_words,
        "files": {
            name: {"raw": d["raw"], "language": d["language"]} for name, d in file_data.items()
        },
    }
    with open(_raw_texts_path(scan_uuid), "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _load_raw_texts(scan_uuid: str) -> tuple[dict, int] | None:
    """Return `(texts_by_name, min_match_words)`, or None if unreadable."""
    path = _raw_texts_path(scan_uuid)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        # A truncated or unreadable sidecar means the comparison simply
        # isn't available — not a server fault worth a 500.
        return None
    return payload.get("files", {}), int(payload.get("min_match_words", 0))


@app.route("/api/status", methods=["GET"])
def api_status():
    """Liveness check."""
    return jsonify({"status": "ok", "service": "plagcheck", "version": "3.2.0"})


@app.route("/api/modes", methods=["GET"])
def api_modes():
    """List the available scanning modes."""
    return jsonify({"modes": sorted(VALID_MODES)})


@app.route("/api/algorithms", methods=["GET"])
def api_algorithms():
    """List the algorithm choices selectable per mode.

    "auto" is the default and scores by matched-span coverage, so the score
    equals the fraction of the document the comparison view highlights. The
    rest force a single named model, for demoing/reviewing each algorithm
    individually — their raw scores are not coverage and need not line up
    with the highlighting.
    """
    return jsonify({
        "algorithms": sorted({a for choices in ALGORITHMS_BY_MODE.values() for a in choices}),
        "by_mode": ALGORITHMS_BY_MODE,
    })


@app.route("/api/detect-language", methods=["POST"])
def api_detect_language():
    """Guess which of python/java/c/cpp a pasted code snippet is written in.

    Used by the paste-box UI in code_similarity mode so the right
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

    if not (0.0 < threshold < 1.0):
        return _error("threshold must be between 0 and 1.", "invalid_threshold", 400)

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
    name_counts: dict[str, int] = {}

    with tempfile.TemporaryDirectory(prefix="plagcheck_") as sandbox:
        for index, upload in enumerate(uploads):
            # Strip any directory component a hostile client might smuggle
            # into the filename field. Deliberately NOT running this through
            # secure_filename(): that ASCII-transliterates/strips characters
            # (e.g. Turkish "İ" silently becomes "I"), which would desync
            # this display name from the original `File.name` the browser
            # (and thus the frontend, matching by that exact string) holds.
            # The physical sandbox path below uses a separate, synthetic
            # ASCII-safe name, so this name never touches the filesystem.
            original_name = os.path.basename((upload.filename or "").replace("\\", "/")).strip()
            if not original_name:
                errors.append({"file": upload.filename, "error": "Unsafe or missing filename"})
                continue

            ext = os.path.splitext(original_name)[1].lower()
            if not is_allowed_for_mode(ext, mode):
                errors.append({
                    "file": upload.filename,
                    "error": f"Format {ext or '(none)'} is not accepted by mode '{mode}'",
                })
                continue

            # Two uploads sharing an original filename (e.g. the same file
            # placed in both the reference and candidate slots) would
            # otherwise collide in file_data/matrix names — disambiguate the
            # display name. The on-disk path is already unique per upload
            # index, so this only affects what's shown/matched by name.
            occurrence = name_counts.get(original_name, 0)
            name_counts[original_name] = occurrence + 1
            if occurrence:
                stem, dupe_ext = os.path.splitext(original_name)
                display_name = f"{stem} ({occurrence + 1}){dupe_ext}"
            else:
                display_name = original_name

            # loader.py's SAFE_RE only allows [A-Za-z0-9._-] on disk paths;
            # a synthetic per-upload name sidesteps that without mangling
            # the original (possibly non-ASCII, possibly duplicate) name
            # used everywhere else.
            path = os.path.join(sandbox, f"upload_{index}{ext}")
            try:
                upload.save(path)
            except OSError as e:
                errors.append({"file": display_name, "error": f"Could not read upload: {e}"})
                continue
            try:
                raw_text = loader.load(path, mode=mode)
                language = language_for_extension(ext) or "text"
                tokens, kgrams = preprocessor.process(raw_text, language=language)
                file_data[display_name] = {
                    "raw": raw_text,
                    "tokens": tokens,
                    "kgrams": kgrams,
                    "language": language,
                }
                files_meta.append({
                    "file_name": display_name,
                    "file_size_bytes": os.path.getsize(path),
                    "file_format": ext.lstrip(".").lower(),
                })
            except FileLoadError as e:
                errors.append({"file": display_name, "error": str(e)})
                audit.log(
                    "FILE_REJECTED",
                    scan_uuid=scan_uuid,
                    payload={"file": display_name, "error": str(e)},
                )

    # A single uploaded file is a valid scan (it just has no other file to
    # be compared against, so its matrix/pairs come back empty).
    if not file_data:
        return _error(
            f"Need at least 1 valid file for mode '{mode}'.",
            "insufficient_files",
            400,
            scan_id=scan_uuid,
            file_errors=errors,
        )

    engine = ScanEngine(mode=mode, algorithm=algorithm)
    result = engine.compute(file_data, preprocessor=preprocessor, min_match_words=min_match_words)

    assert result.matrix is not None  # guaranteed by ScanEngine.compute
    matrix_payload = {
        "names": result.matrix.names,
        "scores": result.matrix.as_numpy().tolist(),
    }
    pairs_payload = [
        {**p, "flagged": p["score"] >= threshold} for p in result.matrix.all_pairs()
    ]

    repository.save_scan(mode, threshold, files_meta, result, scan_uuid)
    _save_raw_texts(scan_uuid, file_data, min_match_words)

    audit.log(
        "SCAN_COMPLETE",
        scan_uuid=scan_uuid,
        payload={"flagged_count": sum(1 for p in pairs_payload if p["flagged"])},
    )

    return jsonify({
        "scan_id": scan_uuid,
        "mode": mode,
        "algorithm": algorithm,
        "threshold": threshold,
        "min_match_words": min_match_words,
        "matrix": matrix_payload,
        "pairs": pairs_payload,
        "similarity_indices": result.similarity_indices,
        "source_breakdowns": result.source_breakdowns,
        "errors": errors,
    })


@app.route("/api/report/<scan_uuid>", methods=["GET"])
def api_report(scan_uuid):
    """Return a persisted scan's file list, mode, threshold, and results."""
    record = repository.get_scan(scan_uuid)
    if record is None:
        return _error("Report not found.", "not_found", 404)
    return jsonify(record)


def _pair_payload(scan_uuid: str, file_a: str, file_b: str):
    """Resolve one pair's raw texts and filtered matched spans.

    Returns `(texts, spans_a, spans_b)`, or an `(error_response, status)`
    tuple ready to return. Shared by the JSON inspector endpoint and the PDF
    export so the two can never highlight different things.
    """
    loaded = _load_raw_texts(scan_uuid)
    if loaded is None:
        return _error("Pair not found.", "not_found", 404)
    texts, stored_min_match_words = loaded
    if file_a not in texts or file_b not in texts:
        return _error("Pair not found.", "not_found", 404)

    # Defaults to whatever the scan itself used, so the highlighting matches
    # the score the user is looking at; overridable for exploration.
    try:
        min_match_words = int(request.args.get("min_match_words", stored_min_match_words))
    except (TypeError, ValueError):
        return _error("min_match_words must be an integer.", "invalid_min_match_words", 400)

    preprocessor = Preprocessor()
    spans_a, spans_b = matched_spans(
        texts[file_a]["raw"],
        texts[file_b]["raw"],
        texts[file_a]["language"],
        texts[file_b]["language"],
        preprocessor,
    )
    return (
        texts,
        _filter_by_word_count(texts[file_a]["raw"], spans_a, min_match_words),
        _filter_by_word_count(texts[file_b]["raw"], spans_b, min_match_words),
    )


@app.route("/api/report/<scan_uuid>/pair/<file_a>/<file_b>", methods=["GET"])
def api_report_pair(scan_uuid, file_a, file_b):
    """Return both files' raw text plus matched-span offsets for the inspector."""
    resolved = _pair_payload(scan_uuid, file_a, file_b)
    if len(resolved) == 2:  # (error_response, status)
        return resolved
    texts, spans_a, spans_b = resolved

    return jsonify({
        "file_a": {"name": file_a, "text": texts[file_a]["raw"], "matched_spans": spans_a},
        "file_b": {"name": file_b, "text": texts[file_b]["raw"], "matched_spans": spans_b},
    })


def _content_disposition(filename: str) -> str:
    """Build an attachment header that survives non-ASCII filenames.

    Emits an ASCII-only `filename=` for older clients plus the RFC 5987
    `filename*=UTF-8''…` form every current browser prefers — a Turkish
    display name would otherwise be mangled or rejected outright.
    """
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@app.route("/api/report/<scan_uuid>/pair-pdf/<file_a>/<file_b>", methods=["GET"])
def api_report_pair_pdf(scan_uuid, file_a, file_b):
    """Export one comparison as a PDF with the matched regions highlighted.

    Mounted at `pair-pdf/` rather than `pair/….pdf`: Flask's default string
    converter would let the existing pair route swallow a `.pdf` suffix as
    part of `file_b`, making the two routes ambiguous.

    The score/threshold/mode shown in the header come from the persisted scan
    record, never from query parameters, so the PDF cannot be made to state a
    score the scan never produced.
    """
    resolved = _pair_payload(scan_uuid, file_a, file_b)
    if len(resolved) == 2:  # (error_response, status)
        return resolved
    texts, spans_a, spans_b = resolved

    record = repository.get_scan(scan_uuid) or {}
    score = next(
        (
            p["score"]
            for p in record.get("pairs", [])
            if {p["file_a"], p["file_b"]} == {file_a, file_b}
        ),
        None,
    )

    pdf = ReportGenerator().pair_pdf_bytes(
        file_a,
        texts[file_a]["raw"],
        spans_a,
        file_b,
        texts[file_b]["raw"],
        spans_b,
        score=score,
        threshold=record.get("threshold"),
        mode=record.get("algorithm"),
        algorithm=record.get("algorithm_override"),
    )
    stem_a = os.path.splitext(file_a)[0]
    stem_b = os.path.splitext(file_b)[0]
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": _content_disposition(f"{stem_a} vs {stem_b}.pdf")},
    )


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
