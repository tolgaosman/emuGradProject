""" loader.py — File ingestion and validation. """
import os
import re

import chardet
import fitz
import pdfplumber
from docx import Document as DocxDocument

SUPPORTED = {".txt", ".py", ".pdf", ".docx"}
MAX_BYTES = 10 * 1024 * 1024
MAX_FILES = 50
SAFE_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


class FileLoadError(Exception):
    """Raised when a file fails ingestion validation or extraction."""


class FileLoader:
    """Validates and extracts text from an uploaded/on-disk file."""

    def load(self, path: str) -> str:
        """Validate `path` and return its extracted text."""
        self._validate(path)
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            return self._load_pdf(path)
        if ext == ".docx":
            return self._load_docx(path)
        return self._load_text(path)

    def load_batch(self, paths: list[str]) -> dict[str, str]:
        """Load every path in `paths`, enforcing the batch size limit.

        Returns a mapping of basename -> extracted text for files that load
        successfully; callers are responsible for surfacing per-file errors
        raised by `load()` for the rest.
        """
        if len(paths) > MAX_FILES:
            raise FileLoadError(f"Batch of {len(paths)} exceeds max of {MAX_FILES} files.")
        return {os.path.basename(p): self.load(p) for p in paths}

    def _validate(self, path):
        name = os.path.basename(path)
        if not SAFE_RE.match(name):
            raise FileLoadError(f"Unsafe filename: {name}")
        # Reject '..' as a literal path component (not merely a substring),
        # so a legitimate name like 'my..dir/a.txt' is not falsely rejected
        # while './../secret.txt' still is.
        parts = re.split(r"[\\/]", path)
        if ".." in parts:
            raise FileLoadError(f"Path traversal: {path}")
        if os.path.splitext(path)[1].lower() not in SUPPORTED:
            raise FileLoadError(f"Unsupported format: {path}")
        if os.path.islink(path):
            raise FileLoadError(f"Symlinks are not allowed: {path}")
        try:
            size = os.path.getsize(path)
        except OSError as e:
            raise FileLoadError(f"Cannot read file: {path} ({e})") from e
        if size == 0:
            raise FileLoadError(f"File is empty: {path}")
        if size > MAX_BYTES:
            raise FileLoadError(f"File > 10 MB: {path}")

    def _load_pdf(self, path: str) -> str:
        """Extract text via pdfplumber, falling back to PyMuPDF."""
        try:  # Stage 1: pdfplumber
            with pdfplumber.open(path) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
                if text:
                    return text
        except Exception:
            pass
        try:  # Stage 2: PyMuPDF fallback
            with fitz.open(path) as doc:
                text = "\n".join(str(page.get_text("text")) for page in doc).strip()
                if text:
                    return text
        except Exception:
            pass
        raise FileLoadError(f"No extractable text (image-only?): {path}")

    def _load_text(self, path: str) -> str:
        """Read a .txt/.py file, sniffing its encoding via chardet."""
        with open(path, "rb") as f:
            raw = f.read(10_000)
        detected = chardet.detect(raw)
        confidence = detected.get("confidence") or 0.0
        encoding = detected.get("encoding")
        if not encoding or confidence < 0.75:
            raise FileLoadError(f"Low encoding confidence: {path}")
        with open(path, encoding=encoding, errors="replace") as f:
            return f.read()

    def _load_docx(self, path: str) -> str:
        """Extract paragraph text from a .docx file."""
        return "\n".join(p.text for p in DocxDocument(path).paragraphs)
