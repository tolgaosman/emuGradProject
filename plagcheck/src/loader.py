""" loader.py — File ingestion and validation. """ 
# pyrefly: ignore [missing-import]
import os, re, chardet, pdfplumber, fitz 
# pyrefly: ignore [missing-import]
from docx import Document as DocxDocument 

SUPPORTED = {".txt", ".py", ".pdf", ".docx"} 
MAX_BYTES = 10 * 1024 * 1024 
SAFE_RE = re.compile(r"^[A-Za-z0-9._\-]+$") 

class FileLoadError(Exception): pass 

class FileLoader: 
    def load(self, path: str) -> str: 
        self._validate(path) 
        ext = os.path.splitext(path)[1].lower() 
        if ext == ".pdf": return self._load_pdf(path) 
        if ext == ".docx": return self._load_docx(path) 
        return self._load_text(path) 

    def _validate(self, path):
        name = os.path.basename(path)
        if not SAFE_RE.match(name):
            raise FileLoadError(f"Unsafe filename: {name}")
        if ".." in path:
            raise FileLoadError(f"Path traversal: {path}")
        if os.path.splitext(path)[1].lower() not in SUPPORTED:
            raise FileLoadError(f"Unsupported format: {path}")
        if os.path.getsize(path) > MAX_BYTES:
            raise FileLoadError(f"File > 10 MB: {path}")

    def _load_pdf(self, path): 
        try: # Stage 1: pdfplumber 
            with pdfplumber.open(path) as pdf: 
                t = "\n".join(p.extract_text() or "" for p in pdf.pages).strip() 
                if t: return t 
        except Exception: pass 
        try: # Stage 2: PyMuPDF fallback 
            doc = fitz.open(path) 
            t = "\n".join(doc[i].get_text("text") for i in range(len(doc))).strip() 
            if t: return t 
        except Exception: pass 
        raise FileLoadError(f"No extractable text (image-only?): {path}") 

    def _load_text(self, path):
        with open(path, "rb") as f:
            raw = f.read(10_000)
        r = chardet.detect(raw)
        if r["confidence"] < 0.75:
            raise FileLoadError(f"Low encoding confidence: {path}")
        with open(path, encoding=r["encoding"], errors="replace") as f:
            return f.read()

    def _load_docx(self, path): 
        return "\n".join(p.text for p in DocxDocument(path).paragraphs) 
