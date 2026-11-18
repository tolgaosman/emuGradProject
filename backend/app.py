""" app.py — Flask REST API. """
import logging
import os
import re
import tempfile
import time
import unicodedata
import uuid
import zipfile
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
from src.models import ASTModel, CosineModel, JaccardModel, WinnowingModel
from src.preprocessor import Preprocessor, load_raw_exclusion_terms
from src.reporter import ReportGenerator, matched_spans, paired_spans
from src.repository import ScanRepository
from src.similarity_index import DEFAULT_MIN_MATCH_WORDS, filter_by_word_count, pair_score

load_dotenv()

_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("plagcheck.api")

API_VERSION = "4.0.0"
#: Report UC-03: the threshold is a fraction strictly inside (0, 1).
MIN_THRESHOLD, MAX_THRESHOLD = 0.01, 0.99
#: `scan_file.file_name` is VARCHAR(255); longer names would silently push
#: the whole scan into the JSON fallback.
MAX_NAME_LENGTH = 255
PASTE_CHAR_LIMIT = 15_000
MAX_HISTORY = 100
MAX_CUSTOM_EXCLUSIONS = 200
_SAMPLES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "samples"))
_SAMPLE_PRESETS: dict[str, tuple[str, list[str]]] = {
    "text": (
        "text_similarity",
        ["sample_a.txt", "sample_b.txt", "sample_c.docx", "sample_d.pdf"],
    ),
    "code": ("code_similarity", ["sample_code_a.py", "sample_code_b.py"]),
}
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


def _preprocessor_for(
    excluded_terms: tuple[str, ...] = (), use_default_exclusions: bool = True
) -> Preprocessor:
    """Return the cached default pipeline, or a custom one when exclusions differ."""
    if not excluded_terms and use_default_exclusions:
        return _preprocessor()
    return Preprocessor(
        extra_exclusions=excluded_terms, use_default_exclusions=use_default_exclusions
    )


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
    """Validated scan settings from the multipart form or sample preset."""

    mode: str
    algorithm: str
    threshold: float
    min_match_words: int
    excluded_terms: tuple[str, ...] = ()
    use_default_exclusions: bool = True


@dataclass
class StagedBatch:
    """Uploads that were extracted and preprocessed, plus per-file rejections."""

    file_data: dict = field(default_factory=dict)
    files_meta: list[dict] = field(default_factory=list)
    file_infos: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def _parse_excluded_terms(raw: str | list | None) -> tuple[str, ...]:
    if not raw:
        return ()
    if isinstance(raw, list):
        items = [str(x).strip().lower() for x in raw]
    else:
        items = [part.strip().lower() for part in re.split(r"[,\n;]+", str(raw))]
    cleaned = [t for t in items if t][:MAX_CUSTOM_EXCLUSIONS]
    return tuple(dict.fromkeys(cleaned))


def _parse_bool(raw, default: bool = True) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _validate_params(
    raw_mode, raw_algo, raw_threshold, raw_min_words, raw_excluded=None, raw_use_default=None
) -> CheckParams:
    mode = str(raw_mode if raw_mode is not None else DEFAULT_MODE).lower()
    if mode not in MODES:
        raise _reject(f"Invalid mode '{mode}'.", "invalid_mode", choices=sorted(MODES))

    algorithm = str(raw_algo if raw_algo is not None else "auto").lower()
    choices = ALGORITHMS_BY_MODE.get(mode, [])
    if algorithm not in choices:
        raise _reject(
            f"Algorithm '{algorithm}' is not available for mode '{mode}'.",
            "invalid_algorithm",
            choices=choices,
        )

    try:
        threshold = float(raw_threshold if raw_threshold is not None else DEFAULT_THRESHOLD)
    except (ValueError, TypeError):
        raise _reject("threshold must be a number.", "invalid_threshold") from None
    if not MIN_THRESHOLD <= threshold <= MAX_THRESHOLD:
        raise _reject(
            f"threshold must be between {MIN_THRESHOLD} and {MAX_THRESHOLD}.", "invalid_threshold"
        )

    try:
        min_match_words = int(
            raw_min_words if raw_min_words is not None else DEFAULT_MIN_MATCH_WORDS
        )
    except (ValueError, TypeError):
        raise _reject("min_match_words must be an integer.", "invalid_min_match_words") from None
    if min_match_words < 0:
        raise _reject("min_match_words cannot be negative.", "invalid_min_match_words")

    return CheckParams(
        mode=mode,
        algorithm=algorithm,
        threshold=threshold,
        min_match_words=min_match_words,
        excluded_terms=_parse_excluded_terms(raw_excluded),
        use_default_exclusions=_parse_bool(raw_use_default, True),
    )


def _parse_check_params() -> CheckParams:
    return _validate_params(
        request.form.get("mode", DEFAULT_MODE),
        request.form.get("algorithm", "auto"),
        request.form.get("threshold", DEFAULT_THRESHOLD),
        request.form.get("min_match_words", DEFAULT_MIN_MATCH_WORDS),
        request.form.get("excluded_terms"),
        request.form.get("use_default_exclusions"),
    )


def _unique_name(name: str, seen: dict[str, int]) -> str:
    """Disambiguate a repeated display name as `stem (2).ext`, `stem (3).ext`, ..."""
    occurrence = seen.get(name, 0)
    seen[name] = occurrence + 1
    if not occurrence:
        return name
    stem, ext = os.path.splitext(name)
    return f"{stem} ({occurrence + 1}){ext}"


def _ingest_saved_file(
    path: str,
    display_name: str,
    ext: str,
    index: int,
    mode: str,
    scan_uuid: str,
    loader: FileLoader,
    preprocessor: Preprocessor,
    batch: StagedBatch,
) -> None:
    try:
        raw_text = loader.load(path, mode=mode, display_name=display_name)
    except (OSError, FileLoadError) as e:
        message = str(e) if isinstance(e, FileLoadError) else "Could not read upload."
        batch.errors.append({"file": display_name, "error": message})
        audit.log(
            "FILE_REJECTED",
            scan_uuid=scan_uuid,
            payload={"file": display_name, "error": message},
        )
        return

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


def _expand_zip_upload(
    zip_path: str,
    archive_label: str,
    base_index: int,
    mode: str,
    scan_uuid: str,
    sandbox: str,
    seen: dict[str, int],
    loader: FileLoader,
    preprocessor: Preprocessor,
    batch: StagedBatch,
) -> None:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            extracted_any = False
            for m_idx, info in enumerate(members):
                parts = info.filename.replace("\\", "/").split("/")
                if any(part.startswith(".") or part == "__MACOSX" for part in parts):
                    continue
                member_name = _display_name(info.filename)
                if not member_name:
                    continue
                m_ext = os.path.splitext(member_name)[1].lower()
                if not is_allowed_for_mode(m_ext, mode):
                    continue
                if len(batch.file_data) >= MAX_FILES:
                    batch.errors.append({
                        "file": member_name,
                        "error": f"Skipped: batch limit of {MAX_FILES} files reached.",
                    })
                    continue
                if info.file_size == 0 or info.file_size > MAX_BYTES:
                    batch.errors.append({
                        "file": member_name,
                        "error": "Empty or exceeds 10 MB limit inside archive.",
                    })
                    continue
                extracted_any = True
                display_name = _unique_name(member_name, seen)
                dest = os.path.join(sandbox, f"upload_{base_index}_{m_idx}{m_ext}")
                with zf.open(info) as src_f, open(dest, "wb") as dst_f:
                    dst_f.write(src_f.read(MAX_BYTES + 1))
                _ingest_saved_file(
                    dest,
                    display_name,
                    m_ext,
                    base_index + m_idx,
                    mode,
                    scan_uuid,
                    loader,
                    preprocessor,
                    batch,
                )
            if not extracted_any:
                batch.errors.append({
                    "file": archive_label,
                    "error": f"No valid files for mode '{mode}' found inside archive.",
                })
    except (zipfile.BadZipFile, OSError):
        batch.errors.append({"file": archive_label, "error": "Corrupt or unreadable .zip archive."})


def _stage_uploads(
    uploads, mode: str, scan_uuid: str, sandbox: str, preprocessor: Preprocessor
) -> StagedBatch:
    """Save, validate, extract and preprocess every upload inside `sandbox`."""
    loader = FileLoader()
    batch = StagedBatch()
    seen: dict[str, int] = {}

    for index, upload in enumerate(uploads):
        original = _display_name(upload.filename)
        if not original:
            batch.errors.append({"file": "(unnamed)", "error": "Missing or unsafe filename"})
            continue

        ext = os.path.splitext(original)[1].lower()
        if ext == ".zip":
            zip_path = os.path.join(sandbox, f"archive_{index}.zip")
            try:
                upload.save(zip_path)
            except OSError:
                batch.errors.append({"file": original, "error": "Could not read upload."})
                continue
            _expand_zip_upload(
                zip_path,
                original,
                index,
                mode,
                scan_uuid,
                sandbox,
                seen,
                loader,
                preprocessor,
                batch,
            )
            continue

        if not is_allowed_for_mode(ext, mode):
            batch.errors.append({
                "file": original,
                "error": f"Format {ext or '(none)'} is not accepted by mode '{mode}'",
            })
            continue

        if len(batch.file_data) >= MAX_FILES:
            batch.errors.append({
                "file": original,
                "error": f"Batch limit of {MAX_FILES} files reached.",
            })
            continue

        display_name = _unique_name(original, seen)
        path = os.path.join(sandbox, f"upload_{index}{ext}")
        try:
            upload.save(path)
        except OSError:
            batch.errors.append({"file": display_name, "error": "Could not read upload."})
            continue
        _ingest_saved_file(
            path, display_name, ext, index, mode, scan_uuid, loader, preprocessor, batch
        )
    return batch


def _summary(pairs: list[dict]) -> dict:
    scores = [p["score"] for p in pairs]
    return {
        "pair_count": len(pairs),
        "flagged_count": sum(1 for p in pairs if p["flagged"]),
        "max_score": max(scores, default=0.0),
        "mean_score": sum(scores) / len(scores) if scores else 0.0,
    }


def _execute_scan(
    batch: StagedBatch,
    params: CheckParams,
    scan_uuid: str,
    started: float,
    preprocessor: Preprocessor,
):
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
            batch.file_data, preprocessor=preprocessor, min_match_words=params.min_match_words
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
            source_breakdowns=result.source_breakdowns,
            excluded_terms=list(params.excluded_terms),
            use_default_exclusions=params.use_default_exclusions,
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


@app.route("/api/check", methods=["POST"])
def api_check():
    """Run a scan over uploaded files (multipart/form-data)."""
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

    preprocessor = _preprocessor_for(params.excluded_terms, params.use_default_exclusions)
    with tempfile.TemporaryDirectory(prefix="plagcheck_") as sandbox:
        batch = _stage_uploads(uploads, params.mode, scan_uuid, sandbox, preprocessor)

    return _execute_scan(batch, params, scan_uuid, started, preprocessor)


@app.route("/api/check-sample", methods=["POST"])
def api_check_sample():
    """Run a scan over built-in sample fixtures (`text` or `code`) for 1-click demos."""
    body = request.get_json(silent=True) or {}
    preset = str(body.get("preset", "text")).lower()
    if preset not in _SAMPLE_PRESETS:
        raise _reject(
            f"Invalid sample preset '{preset}'.",
            "invalid_preset",
            choices=sorted(_SAMPLE_PRESETS),
        )
    preset_mode, filenames = _SAMPLE_PRESETS[preset]
    params = _validate_params(
        preset_mode,
        body.get("algorithm", "auto"),
        body.get("threshold", DEFAULT_THRESHOLD),
        body.get("min_match_words", DEFAULT_MIN_MATCH_WORDS),
        body.get("excluded_terms"),
        body.get("use_default_exclusions"),
    )

    scan_uuid = str(uuid.uuid4())
    started = time.perf_counter()
    audit.log(
        "SCAN_START",
        scan_uuid=scan_uuid,
        payload={
            "files": filenames,
            "mode": params.mode,
            "algorithm": params.algorithm,
            "threshold": params.threshold,
            "sample_preset": preset,
        },
    )

    loader = FileLoader()
    preprocessor = _preprocessor_for(params.excluded_terms, params.use_default_exclusions)
    batch = StagedBatch()
    for index, fname in enumerate(filenames):
        sample_path = os.path.join(_SAMPLES_DIR, fname)
        ext = os.path.splitext(fname)[1].lower()
        _ingest_saved_file(
            sample_path, fname, ext, index, params.mode, scan_uuid, loader, preprocessor, batch
        )

    return _execute_scan(batch, params, scan_uuid, started, preprocessor)


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


@app.route("/api/exclusions", methods=["GET"])
def api_exclusions():
    """Return the built-in 50-term academic exclusion list (FR-15 / UC-12)."""
    terms = load_raw_exclusion_terms()
    return jsonify({"terms": terms, "count": len(terms)})


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
    """Resolve one pair's raw texts, filtered matched spans, and preprocessor.

    Returns `(texts, spans_a, spans_b, min_match_words, preprocessor)`. Shared
    by the JSON inspector endpoint and the PDF export so the two can never
    highlight different things.
    """
    sidecar = repository.load_sidecar(scan_uuid)
    if sidecar is None:
        raise ApiError("Pair not found.", "not_found", 404)
    texts = sidecar.get("files", {})
    stored_min_match_words = int(sidecar.get("min_match_words", 0))
    if file_a not in texts or file_b not in texts:
        raise ApiError("Pair not found.", "not_found", 404)

    try:
        min_match_words = int(request.args.get("min_match_words", stored_min_match_words))
    except (TypeError, ValueError):
        raise ApiError("min_match_words must be an integer.", "invalid_min_match_words") from None

    preprocessor = _preprocessor_for(
        tuple(sidecar.get("excluded_terms") or ()),
        bool(sidecar.get("use_default_exclusions", True)),
    )
    spans_a, spans_b = matched_spans(
        texts[file_a]["raw"],
        texts[file_b]["raw"],
        texts[file_a]["language"],
        texts[file_b]["language"],
        preprocessor,
    )
    return (
        texts,
        filter_by_word_count(texts[file_a]["raw"], spans_a, min_match_words),
        filter_by_word_count(texts[file_b]["raw"], spans_b, min_match_words),
        min_match_words,
        preprocessor,
    )


def _pair_stats(
    texts: dict,
    file_a: str,
    file_b: str,
    spans_a: list[tuple[int, int]],
    spans_b: list[tuple[int, int]],
    preprocessor: Preprocessor,
) -> tuple[int, dict]:
    raw_a, lang_a = texts[file_a]["raw"], texts[file_a]["language"]
    raw_b, lang_b = texts[file_b]["raw"], texts[file_b]["language"]
    tokens_a, kgrams_a = preprocessor.process(raw_a, lang_a)
    tokens_b, kgrams_b = preprocessor.process(raw_b, lang_b)
    matched_kg = len(set(kgrams_a) & set(kgrams_b))
    ast_score = (
        round(ASTModel().compute([raw_a], [raw_b]), 4)
        if lang_a == "python" and lang_b == "python"
        else None
    )
    algo_scores = {
        "coverage": round(pair_score(raw_a, raw_b, spans_a, spans_b), 4),
        "cosine": round(CosineModel().compute(tokens_a, tokens_b), 4),
        "winnowing": round(WinnowingModel().compute(tokens_a, tokens_b), 4),
        "jaccard": round(JaccardModel().compute(tokens_a, tokens_b), 4),
        "ast": ast_score,
    }
    return matched_kg, algo_scores


@app.route("/api/report/<uuid:scan_uuid>/pair/<file_a>/<file_b>", methods=["GET"])
def api_report_pair(scan_uuid, file_a, file_b):
    """Return both files' raw text, spans, linked match blocks, and 4-algo breakdown."""
    texts, spans_a, spans_b, min_match_words, preprocessor = _pair_payload(
        str(scan_uuid), file_a, file_b
    )
    matched_kg, algo_scores = _pair_stats(
        texts, file_a, file_b, spans_a, spans_b, preprocessor
    )
    linked = paired_spans(
        texts[file_a]["raw"],
        texts[file_b]["raw"],
        texts[file_a]["language"],
        texts[file_b]["language"],
        preprocessor,
        min_match_words=min_match_words,
    )
    return jsonify({
        "file_a": {"name": file_a, "text": texts[file_a]["raw"], "matched_spans": spans_a},
        "file_b": {"name": file_b, "text": texts[file_b]["raw"], "matched_spans": spans_b},
        "paired_spans": linked,
        "algorithm_scores": algo_scores,
        "matched_kgrams": matched_kg,
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
    texts, spans_a, spans_b, _, _ = _pair_payload(scan_uuid, file_a, file_b)

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
