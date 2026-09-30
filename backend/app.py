""" app.py — Flask REST API. """
import logging
import os
import re
import tempfile
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import quote

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from src.audit import AuditLogger
from src.engine import ALGORITHMS_BY_MODE, ScanEngine
from src.language import MODES, detect_language, is_allowed_for_mode, language_for_extension
from src.loader import MAX_BYTES, MAX_FILES, FileLoader, FileLoadError
from src.matrix import ComparisonMatrix
from src.preprocessor import Preprocessor
from src.reporter import ReportGenerator, matched_spans
from src.repository import ScanRepository
from src.similarity_index import DEFAULT_MIN_MATCH_WORDS, filter_by_word_count

load_dotenv()

_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("plagcheck.api")

API_VERSION = "3.3.0"
#: Report UC-03: the threshold is a fraction strictly inside (0, 1).
MIN_THRESHOLD, MAX_THRESHOLD = 0.01, 0.99
#: `scan_file.file_name` is VARCHAR(255); longer names would silently push
#: the whole scan into the JSON fallback.
MAX_NAME_LENGTH = 255
PASTE_CHAR_LIMIT = 15_000
MAX_HISTORY = 100
_WORD_RE = re.compile(r"\w+")
_STARTED_AT = time.monotonic()


def _env_threshold() -> float:
    raw = os.environ.get("DEFAULT_THRESHOLD", "0.70")
    try:
        value = float(raw)
    except ValueError:
        value = -1.0
    if not MIN_THRESHOLD <= value <= MAX_THRESHOLD:
        logger.warning("Ignoring invalid DEFAULT_THRESHOLD=%r; using 0.70", raw)
        return 0.70
    return value


def _env_mode() -> str:
    mode = os.environ.get("DEFAULT_MODE", "text_similarity").lower()
    if mode not in MODES:
        logger.warning("Ignoring invalid DEFAULT_MODE=%r; using text_similarity", mode)
        return "text_similarity"
    return mode


DEFAULT_THRESHOLD = _env_threshold()
DEFAULT_MODE = _env_mode()

app = Flask(__name__)
# 50 files * 10 MB/file, plus headroom for multipart form overhead.
app.config["MAX_CONTENT_LENGTH"] = MAX_FILES * MAX_BYTES + (1 * 1024 * 1024)
CORS(app, resources={r"/api/*": {"origins": os.environ.get("CORS_ORIGIN", "http://localhost:5173")}})

audit = AuditLogger()
repository = ScanRepository()
reporter = ReportGenerator()


@lru_cache(maxsize=1)
def _preprocessor() -> Preprocessor:
    """One shared pipeline: building it re-stems the whole stopword list."""
    return Preprocessor()


class ApiError(Exception):
    """A client-facing failure, rendered as the `{error, code, ...}` envelope."""

    def __init__(self, message: str, code: str, status: int = 400, **extra):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.extra = extra


def _error(message: str, code: str, status: int, **extra):
    return jsonify({"error": message, "code": code, **extra}), status


_HTTP_CODES = {
    404: ("Not found.", "not_found"),
    405: ("Method not allowed.", "method_not_allowed"),
    413: (
        f"Upload too large: at most {MAX_FILES} files of {MAX_BYTES // (1024 * 1024)} MB each.",
        "payload_too_large",
    ),
}


@app.errorhandler(ApiError)
def _handle_api_error(e: ApiError):
    return _error(e.message, e.code, e.status, **e.extra)


@app.errorhandler(HTTPException)
def _handle_http_error(e: HTTPException):
    status = e.code or 500
    message, code = _HTTP_CODES.get(status, (e.description or "Request failed.", "http_error"))
    return _error(message, code, status)


@app.errorhandler(Exception)
def _handle_unexpected(e: Exception):
    # Log the traceback server-side; never echo internals to the client.
    logger.exception("Unhandled error on %s %s", request.method, request.path)
    return _error("Something went wrong on the server.", "internal_error", 500)


def _reject(message: str, code: str, status: int = 400, **extra) -> ApiError:
    """Audit a rejected request (FR-14) and build the error to raise."""
    audit.log("API_ERROR", payload={"code": code, "path": request.path})
    return ApiError(message, code, status, **extra)


def _content_disposition(filename: str) -> str:
    """Build an attachment header that survives non-ASCII filenames.

    Emits an ASCII-only `filename=` for older clients plus the RFC 5987
    `filename*=UTF-8''…` form every current browser prefers — a Turkish
    display name would otherwise be mangled or rejected outright.
    """
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _attachment(body, mimetype: str, filename: str) -> Response:
    return Response(
        body, mimetype=mimetype, headers={"Content-Disposition": _content_disposition(filename)}
    )


def _display_name(filename: str | None) -> str:
    """Reduce a client-supplied filename to a safe display name.

    Directory components are stripped and control/format characters (NUL,
    newlines, bidi overrides) removed. Deliberately NOT `secure_filename()`:
    that ASCII-transliterates (Turkish "İ" becomes "I"), which would desync
    this name from the `File.name` the browser holds and matches on. The name
    never touches the filesystem — uploads are staged under synthetic paths.
    """
    name = os.path.basename((filename or "").replace("\\", "/"))
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    if len(name) > MAX_NAME_LENGTH:
        stem, ext = os.path.splitext(name)
        name = stem[: MAX_NAME_LENGTH - len(ext)] + ext
    return name


# -- /api/check ----------------------------------------------------------------


@dataclass(frozen=True)
class CheckParams:
    """Validated scan settings from the multipart form."""

    mode: str
    algorithm: str
    threshold: float
    min_match_words: int


@dataclass
class StagedBatch:
    """Uploads that were extracted and preprocessed, plus per-file rejections."""

    file_data: dict = field(default_factory=dict)
    files_meta: list[dict] = field(default_factory=list)
    file_infos: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def _parse_check_params() -> CheckParams:
    mode = request.form.get("mode", DEFAULT_MODE).lower()
    if mode not in MODES:
        raise _reject(f"Invalid mode '{mode}'.", "invalid_mode", choices=sorted(MODES))

    algorithm = request.form.get("algorithm", "auto").lower()
    choices = ALGORITHMS_BY_MODE.get(mode, [])
    if algorithm not in choices:
        raise _reject(
            f"Algorithm '{algorithm}' is not available for mode '{mode}'.",
            "invalid_algorithm",
            choices=choices,
        )

    try:
        threshold = float(request.form.get("threshold", DEFAULT_THRESHOLD))
    except (ValueError, TypeError):
        raise _reject("threshold must be a number.", "invalid_threshold") from None
    if not MIN_THRESHOLD <= threshold <= MAX_THRESHOLD:
        raise _reject(
            f"threshold must be between {MIN_THRESHOLD} and {MAX_THRESHOLD}.", "invalid_threshold"
        )

    try:
        min_match_words = int(request.form.get("min_match_words", DEFAULT_MIN_MATCH_WORDS))
    except (ValueError, TypeError):
        raise _reject("min_match_words must be an integer.", "invalid_min_match_words") from None
    if min_match_words < 0:
        raise _reject("min_match_words cannot be negative.", "invalid_min_match_words")

    return CheckParams(mode, algorithm, threshold, min_match_words)


def _unique_name(name: str, seen: dict[str, int]) -> str:
    """Disambiguate a repeated display name as `stem (2).ext`, `stem (3).ext`, ..."""
    occurrence = seen.get(name, 0)
    seen[name] = occurrence + 1
    if not occurrence:
        return name
    stem, ext = os.path.splitext(name)
    return f"{stem} ({occurrence + 1}){ext}"


def _stage_uploads(uploads, mode: str, scan_uuid: str, sandbox: str) -> StagedBatch:
    """Save, validate, extract and preprocess every upload inside `sandbox`.

    Each upload is written under a synthetic ASCII name (`upload_<i><ext>`),
    since the loader's filename regex only admits `[A-Za-z0-9._-]`; the
    original — possibly non-ASCII, possibly duplicated — name is kept only
    as the display name the client matches results on.
    """
    loader = FileLoader()
    preprocessor = _preprocessor()
    batch = StagedBatch()
    seen: dict[str, int] = {}

    for index, upload in enumerate(uploads):
        original = _display_name(upload.filename)
        if not original:
            batch.errors.append({"file": "(unnamed)", "error": "Missing or unsafe filename"})
            continue

        ext = os.path.splitext(original)[1].lower()
        if not is_allowed_for_mode(ext, mode):
            batch.errors.append({
                "file": original,
                "error": f"Format {ext or '(none)'} is not accepted by mode '{mode}'",
            })
            continue

        # Two uploads may share a name (e.g. the same file in both the
        # reference and candidate slots); without this they would collide
        # in file_data and the matrix.
        display_name = _unique_name(original, seen)
        path = os.path.join(sandbox, f"upload_{index}{ext}")
        try:
            upload.save(path)
            raw_text = loader.load(path, mode=mode, display_name=display_name)
        except (OSError, FileLoadError) as e:
            message = str(e) if isinstance(e, FileLoadError) else "Could not read upload."
            batch.errors.append({"file": display_name, "error": message})
            audit.log(
                "FILE_REJECTED",
                scan_uuid=scan_uuid,
                payload={"file": display_name, "error": message},
            )
            continue

        language = language_for_extension(ext) or "text"
        tokens, kgrams = preprocessor.process(raw_text, language=language)
        size = os.path.getsize(path)
        batch.file_data[display_name] = {
            "raw": raw_text,
            "tokens": tokens,
            "kgrams": kgrams,
            "language": language,
        }
        batch.files_meta.append({
            "file_name": display_name,
            "file_size_bytes": size,
            "file_format": ext.lstrip("."),
        })
        batch.file_infos.append({
            "name": display_name,
            "index": index,
            "language": language,
            "size_bytes": size,
            "word_count": len(_WORD_RE.findall(raw_text)),
        })
    return batch


def _summary(pairs: list[dict]) -> dict:
    scores = [p["score"] for p in pairs]
    return {
        "pair_count": len(pairs),
        "flagged_count": sum(1 for p in pairs if p["flagged"]),
        "max_score": max(scores, default=0.0),
        "mean_score": sum(scores) / len(scores) if scores else 0.0,
    }


@app.route("/api/check", methods=["POST"])
def api_check():
    """Run a scan over uploaded files (multipart/form-data).

    Files are validated and staged in a temporary sandbox directory that is
    always deleted afterward — the API never accepts server-side file paths,
    since a browser can't send them and doing so would be a file-read
    vulnerability.
    """
    uploads = request.files.getlist("files")
    params = _parse_check_params()
    if not uploads:
        raise _reject("Please upload at least 1 file.", "no_files")
    if len(uploads) > MAX_FILES:
        raise _reject(
            f"Batch of {len(uploads)} exceeds max of {MAX_FILES} files.", "too_many_files"
        )

    scan_uuid = str(uuid.uuid4())
    started = time.perf_counter()
    audit.log(
        "SCAN_START",
        scan_uuid=scan_uuid,
        payload={
            "files": [_display_name(u.filename) for u in uploads],
            "mode": params.mode,
            "algorithm": params.algorithm,
            "threshold": params.threshold,
        },
    )

    with tempfile.TemporaryDirectory(prefix="plagcheck_") as sandbox:
        batch = _stage_uploads(uploads, params.mode, scan_uuid, sandbox)

    # A single valid file is still a valid scan: it just has nothing to be
    # compared against, so its matrix/pairs come back empty.
    if not batch.file_data:
        raise _reject(
            f"Need at least 1 valid file for mode '{params.mode}'.",
            "insufficient_files",
            scan_id=scan_uuid,
            file_errors=batch.errors,
        )

    try:
        engine = ScanEngine(mode=params.mode, algorithm=params.algorithm)
        result = engine.compute(
            batch.file_data, preprocessor=_preprocessor(), min_match_words=params.min_match_words
        )
        pairs = result.pairs(params.threshold)
        repository.save_scan(
            params.mode,
            params.threshold,
            batch.files_meta,
            result,
            scan_uuid,
            min_match_words=params.min_match_words,
        )
        repository.save_texts(
            scan_uuid,
            {n: {"raw": d["raw"], "language": d["language"]} for n, d in batch.file_data.items()},
            params.min_match_words,
        )
    except Exception:
        logger.exception("Scan %s failed", scan_uuid)
        audit.log("SCAN_ERROR", scan_uuid=scan_uuid, payload={"mode": params.mode})
        raise ApiError(
            "The scan could not be completed.", "scan_failed", 500, scan_id=scan_uuid
        ) from None

    summary = _summary(pairs)
    audit.log(
        "SCAN_COMPLETE",
        scan_uuid=scan_uuid,
        payload={
            "files": list(batch.file_data),
            "mode": params.mode,
            "algorithm": params.algorithm,
            "threshold": params.threshold,
            "max_score": summary["max_score"],
            "flagged_count": summary["flagged_count"],
        },
    )

    matrix = result.matrix
    return jsonify({
        "scan_id": scan_uuid,
        "mode": params.mode,
        "algorithm": params.algorithm,
        "threshold": params.threshold,
        "min_match_words": params.min_match_words,
        "matrix": {"names": matrix.names, "scores": matrix.as_numpy().tolist()} if matrix else None,
        "pairs": pairs,
        "flagged": [p for p in pairs if p["flagged"]],
        "summary": summary,
        "files": batch.file_infos,
        "duration_s": round(time.perf_counter() - started, 3),
        "similarity_indices": result.similarity_indices,
        "source_breakdowns": result.source_breakdowns,
        "errors": batch.errors,
    })


# -- Metadata endpoints ----------------------------------------------------------


@app.route("/api/status", methods=["GET"])
def api_status():
    """Liveness check, plus where scans are stored (the UI shows it)."""
    return jsonify({
        "status": "ok",
        "service": "plagcheck",
        "version": API_VERSION,
        "uptime_s": round(time.monotonic() - _STARTED_AT),
        "offline": True,
        "storage": repository.storage_backend(),
    })


@app.route("/api/modes", methods=["GET"])
def api_modes():
    """List the available scanning modes."""
    return jsonify({"modes": sorted(MODES)})


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
        return _error("Text is empty.", "empty_text", 400)
    if len(text) > PASTE_CHAR_LIMIT:
        return _error("Text exceeds the 15,000 character limit.", "text_too_long", 400)

    language, confidence = detect_language(text)
    return jsonify({"language": language, "confidence": confidence})


@app.route("/api/scans", methods=["GET"])
def api_scans():
    """Recent scans, newest first, for reopening past reports."""
    try:
        limit = int(request.args.get("limit", 20))
    except ValueError:
        raise ApiError("limit must be an integer.", "invalid_limit") from None
    return jsonify({"scans": repository.list_scans(max(1, min(limit, MAX_HISTORY)))})


# -- Persisted reports -------------------------------------------------------------


def _require_scan(scan_uuid: str) -> dict:
    record = repository.get_scan(scan_uuid)
    if record is None:
        raise ApiError("Report not found.", "not_found", 404)
    return record


def _matrix_from_record(record: dict) -> ComparisonMatrix:
    names = [f["file_name"] for f in record.get("files", [])]
    matrix = ComparisonMatrix(names)
    index = {name: i for i, name in enumerate(names)}
    for pair in record.get("pairs", []):
        if pair["file_a"] in index and pair["file_b"] in index:
            matrix.set(index[pair["file_a"]], index[pair["file_b"]], pair["score"])
    return matrix


@app.route("/api/report/<uuid:scan_uuid>", methods=["GET"])
def api_report(scan_uuid):
    """Return a persisted scan, rehydrated enough to re-render its results.

    On top of the stored record this adds the rebuilt `matrix`, the
    per-file `similarity_indices`, and the scan's `min_match_words`, so a
    reopened report renders through the same view as a fresh scan.
    """
    scan_uuid = str(scan_uuid)
    record = _require_scan(scan_uuid)
    matrix = _matrix_from_record(record)
    texts = repository.load_texts(scan_uuid)
    min_match_words = record.get("min_match_words")
    if min_match_words is None:
        min_match_words = texts[1] if texts else DEFAULT_MIN_MATCH_WORDS
    return jsonify({
        **record,
        "scan_id": scan_uuid,
        "mode": record.get("mode") or record.get("algorithm"),
        "min_match_words": min_match_words,
        "matrix": {"names": matrix.names, "scores": matrix.as_numpy().tolist()},
        "similarity_indices": {
            f["file_name"]: f["similarity_index"]
            for f in record.get("files", [])
            if f.get("similarity_index") is not None
        },
        "comparison_available": texts is not None,
    })


@app.route("/api/report/<uuid:scan_uuid>", methods=["DELETE"])
def api_report_delete(scan_uuid):
    """Delete a scan's record and stored document text."""
    if not repository.delete_scan(str(scan_uuid)):
        raise ApiError("Report not found.", "not_found", 404)
    return Response(status=204)


def _pair_payload(scan_uuid: str, file_a: str, file_b: str):
    """Resolve one pair's raw texts and filtered matched spans.

    Returns `(texts, spans_a, spans_b, min_match_words)`. Shared by the JSON
    inspector endpoint and the PDF export so the two can never highlight
    different things.
    """
    loaded = repository.load_texts(scan_uuid)
    if loaded is None:
        raise ApiError("Pair not found.", "not_found", 404)
    texts, stored_min_match_words = loaded
    if file_a not in texts or file_b not in texts:
        raise ApiError("Pair not found.", "not_found", 404)

    # Defaults to whatever the scan itself used, so the highlighting matches
    # the score the user is looking at; overridable for exploration.
    try:
        min_match_words = int(request.args.get("min_match_words", stored_min_match_words))
    except (TypeError, ValueError):
        raise ApiError("min_match_words must be an integer.", "invalid_min_match_words") from None

    spans_a, spans_b = matched_spans(
        texts[file_a]["raw"],
        texts[file_b]["raw"],
        texts[file_a]["language"],
        texts[file_b]["language"],
        _preprocessor(),
    )
    return (
        texts,
        filter_by_word_count(texts[file_a]["raw"], spans_a, min_match_words),
        filter_by_word_count(texts[file_b]["raw"], spans_b, min_match_words),
        min_match_words,
    )


def _matched_kgrams(texts: dict, file_a: str, file_b: str) -> int:
    preprocessor = _preprocessor()
    _, kgrams_a = preprocessor.process(texts[file_a]["raw"], texts[file_a]["language"])
    _, kgrams_b = preprocessor.process(texts[file_b]["raw"], texts[file_b]["language"])
    return len(set(kgrams_a) & set(kgrams_b))


@app.route("/api/report/<uuid:scan_uuid>/pair/<file_a>/<file_b>", methods=["GET"])
def api_report_pair(scan_uuid, file_a, file_b):
    """Return both files' raw text plus matched-span offsets for the inspector."""
    texts, spans_a, spans_b, min_match_words = _pair_payload(str(scan_uuid), file_a, file_b)
    return jsonify({
        "file_a": {"name": file_a, "text": texts[file_a]["raw"], "matched_spans": spans_a},
        "file_b": {"name": file_b, "text": texts[file_b]["raw"], "matched_spans": spans_b},
        "matched_kgrams": _matched_kgrams(texts, file_a, file_b),
        "min_match_words": min_match_words,
    })


@app.route("/api/report/<uuid:scan_uuid>/pair-pdf/<file_a>/<file_b>", methods=["GET"])
def api_report_pair_pdf(scan_uuid, file_a, file_b):
    """Export one comparison as a PDF with the matched regions highlighted.

    Mounted at `pair-pdf/` rather than `pair/….pdf`: Flask's default string
    converter would let the existing pair route swallow a `.pdf` suffix as
    part of `file_b`, making the two routes ambiguous.

    The score/threshold/mode shown in the header come from the persisted scan
    record, never from query parameters, so the PDF cannot be made to state a
    score the scan never produced.
    """
    scan_uuid = str(scan_uuid)
    texts, spans_a, spans_b, _ = _pair_payload(scan_uuid, file_a, file_b)

    record = repository.get_scan(scan_uuid) or {}
    score = next(
        (
            p["score"]
            for p in record.get("pairs", [])
            if {p["file_a"], p["file_b"]} == {file_a, file_b}
        ),
        None,
    )

    pdf = reporter.pair_pdf_bytes(
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
    return _attachment(pdf, "application/pdf", f"{stem_a} vs {stem_b}.pdf")


@app.route("/api/report/<uuid:scan_uuid>/matrix.csv", methods=["GET"])
def api_report_csv(scan_uuid):
    """Download the similarity matrix as CSV (FR-09)."""
    scan_uuid = str(scan_uuid)
    matrix = _matrix_from_record(_require_scan(scan_uuid))
    return _attachment(matrix.to_csv(), "text/csv", f"plagcheck-{scan_uuid[:8]}-matrix.csv")


@app.route("/api/report/<uuid:scan_uuid>/report.html", methods=["GET"])
def api_report_html(scan_uuid):
    """Download the self-contained HTML comparison report (FR-09).

    Uses the stored document text when it's still available, so flagged
    pairs get highlighted side-by-side panes; otherwise it degrades to the
    flagged-pairs table alone.
    """
    scan_uuid = str(scan_uuid)
    record = _require_scan(scan_uuid)
    loaded = repository.load_texts(scan_uuid)
    texts, min_match_words = loaded if loaded else (None, 0)
    page = reporter.html_report(
        _matrix_from_record(record),
        record.get("threshold", DEFAULT_THRESHOLD),
        file_data=texts,
        preprocessor=_preprocessor() if texts else None,
        min_match_words=min_match_words,
        pairs=record.get("pairs"),
        algorithm=record.get("algorithm_override"),
    )
    return _attachment(page, "text/html", f"plagcheck-{scan_uuid[:8]}-report.html")


@app.route("/api/report/<uuid:scan_uuid>/heatmap.png", methods=["GET"])
def api_report_heatmap(scan_uuid):
    """Stream the 300 DPI similarity heatmap for a persisted scan.

    `?ref=<name>` renders a single row (that file vs every other); `ref=all`
    or an unknown name renders the full matrix.
    """
    record = _require_scan(str(scan_uuid))
    matrix = _matrix_from_record(record)
    threshold = record.get("threshold", DEFAULT_THRESHOLD)
    names = matrix.names

    ref = request.args.get("ref", names[0] if names else None)
    if ref in names and len(names) > 1:
        i = names.index(ref)
        candidates = [n for n in names if n != ref]
        scores = [matrix.get(i, names.index(c)) for c in candidates]
        png = reporter.single_row_heatmap_png_bytes(ref, candidates, scores, threshold)
    else:
        png = reporter.heatmap_png_bytes(matrix, threshold)
    return Response(png, mimetype="image/png")


if __name__ == "__main__":
    repository.purge_expired()
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        port=int(os.environ.get("APP_PORT", "5000")),
    )
