""" loader.py — File ingestion and validation. """
import logging
import os
import re

import chardet
import pdfplumber
import pymupdf
from docx import Document as DocxDocument

from .language import is_allowed_for_mode

SUPPORTED = {".txt", ".py", ".pdf", ".docx", ".java", ".c", ".h", ".cpp", ".cc", ".hpp"}
MAX_BYTES = 10 * 1024 * 1024
MAX_FILES = 50
SAFE_RE = re.compile(r"^[A-Za-z0-9._\-]+$")
#: Minimum chardet confidence for a non-UTF-8 text file (report §3.2.5);
#: below it the file is rejected rather than decoded into garbage.
MIN_ENCODING_CONFIDENCE = 0.75

logger = logging.getLogger(__name__)


class FileLoadError(Exception):
    """Raised when a file fails ingestion validation or extraction."""


class FileLoader:
    """Validates and extracts text from an uploaded/on-disk file."""

    def load(self, path: str, mode: str | None = None, display_name: str | None = None) -> str:
        """Validate `path` and return its extracted text.

        When `mode` is given, the extension must also be on that mode's
        allow-list (see `language.MODE_EXTENSIONS`) — e.g. a `.py` file is
        rejected in `text_similarity` even though `.py` is a generally
        supported extension.

        `display_name` is what error messages call the file. The API stages
        uploads under synthetic sandbox paths, and those must never leak
        back to the client in place of the name the user actually uploaded.
        Any extraction failure — including a corrupt archive or PDF that
        makes the underlying library raise — surfaces as `FileLoadError`
        (FR-18), never as an unhandled exception.
        """
        label = display_name or path
        self._validate(path, mode, label)
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".pdf":
                return self._load_pdf(path, label)
            if ext == ".docx":
                return self._load_docx(path, label)
            return self._load_text(path, label)
        except FileLoadError:
            raise
        except Exception as e:
            logger.warning("Extraction failed for %s", label, exc_info=True)
            raise FileLoadError(f"Could not parse {label}: the file looks corrupt.") from e

    def load_batch(self, paths: list[str], mode: str | None = None) -> dict[str, str]:
        """Load every path in `paths`, enforcing the batch size limit.

        Returns a mapping of basename -> extracted text for files that load
        successfully; callers are responsible for surfacing per-file errors
        raised by `load()` for the rest.

        Paths sharing a basename (`old/report.txt`, `new/report.txt`) are
        disambiguated as `report (2).txt` rather than overwriting each other
        — same scheme `app.py` and the CLI use for duplicate uploads.
        """
        if len(paths) > MAX_FILES:
            raise FileLoadError(f"Batch of {len(paths)} exceeds max of {MAX_FILES} files.")
        out: dict[str, str] = {}
        counts: dict[str, int] = {}
        for path in paths:
            base = os.path.basename(path)
            occurrence = counts.get(base, 0)
            counts[base] = occurrence + 1
            if occurrence:
                stem, ext = os.path.splitext(base)
                base = f"{stem} ({occurrence + 1}){ext}"
            out[base] = self.load(path, mode)
        return out

    def _validate(self, path: str, mode: str | None, label: str) -> None:
        name = os.path.basename(path)
        if not SAFE_RE.match(name):
            raise FileLoadError(f"Unsafe filename: {name}")
        # Reject '..' as a literal path component (not merely a substring),
        # so a legitimate name like 'my..dir/a.txt' is not falsely rejected
        # while './../secret.txt' still is.
        parts = re.split(r"[\\/]", path)
        if ".." in parts:
            raise FileLoadError(f"Path traversal: {path}")
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED:
            raise FileLoadError(f"Unsupported format: {label}")
        if mode is not None and not is_allowed_for_mode(ext, mode):
            raise FileLoadError(f"Format {ext} is not accepted by mode '{mode}': {label}")
        if os.path.islink(path):
            raise FileLoadError(f"Symlinks are not allowed: {label}")
        try:
            size = os.path.getsize(path)
        except OSError as e:
            raise FileLoadError(f"Cannot read file: {label}") from e
        if size == 0:
            raise FileLoadError(f"File is empty: {label}")
        if size > MAX_BYTES:
            raise FileLoadError(f"File > 10 MB: {label}")

    def _load_pdf(self, path: str, label: str) -> str:
        """Extract text via pdfplumber, falling back to PyMuPDF (FR-03)."""
        try:  # Stage 1: pdfplumber
            with pdfplumber.open(path) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
                if text:
                    return text
        except Exception:
            logger.info("pdfplumber failed on %s; trying PyMuPDF", label, exc_info=True)
        try:  # Stage 2: PyMuPDF fallback
            with pymupdf.open(path) as doc:
                text = "\n".join(str(page.get_text("text")) for page in doc).strip()
                if text:
                    return text
        except Exception:
            logger.info("PyMuPDF failed on %s", label, exc_info=True)
        raise FileLoadError(f"No extractable text (image-only?): {label}")

    def _load_text(self, path: str, label: str) -> str:
        """Read a .txt/source file: strict UTF-8 first, then chardet.

        Most uploads are UTF-8, and chardet can report low confidence on
        short or ASCII-heavy UTF-8 input — decoding strictly first keeps
        those from being rejected. Only non-UTF-8 bytes go through chardet,
        over the whole file (up to the 10 MB cap) so a sample boundary can't
        split a multi-byte character and depress its confidence.
        """
        with open(path, "rb") as f:
            raw = f.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            detected = chardet.detect(raw)
            encoding = detected.get("encoding")
            if not encoding or (detected.get("confidence") or 0.0) < MIN_ENCODING_CONFIDENCE:
                raise FileLoadError(f"Low encoding confidence: {label}") from None
            text = raw.decode(encoding, errors="replace")
        if "\x00" in text:
            raise FileLoadError(f"File looks binary, not text: {label}")
        return text

    def _load_docx(self, path: str, label: str) -> str:
        """Extract paragraph and table-cell text from a .docx file."""
        document = DocxDocument(path)
        chunks = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                chunks.append("\t".join(cell.text for cell in row.cells))
        text = "\n".join(chunks)
        if not text.strip():
            raise FileLoadError(f"No extractable text: {label}")
        return text
