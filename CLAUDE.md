# PlagCheck — Project Guide

PlagCheck is a secure, local-execution plagiarism and file-similarity detection
system built for the CMSE 405 graduation project. It ships as a Python CLI
(`plagcheck/plagcheck.py`), a Flask REST API (`plagcheck/app.py`), and a React
web UI (`web/`).

## The 5 Master Skills (non-negotiable)

1. **Taste** — clean, minimalist whitespace, muted pastel or monochrome
   high-contrast tones (Vercel style), elegant typography. Never use cheap
   default colors or raw CSS grids without intent.
2. **Aesthetic interactions** — organic animations and state transitions on
   every frontend component, smooth easing curves.
3. **Impeccable execution** — pixel-perfection, 60 fps, explicit handling of
   loading states, error rollbacks, empty directories, and unsafe filenames.
4. **Vercel & Anthropic UI/UX** — monochrome design language, user-focused
   simplicity, no visual noise.
5. **Best practices** — modular, DRY, typed, clean code. Strict PEP 8 / PEP 257
   in Python; component-driven React with clean, minimal state.

## Architectural ground truth

Keep every change aligned with this. If a change would contradict it, stop
and flag the conflict instead of silently diverging.

**Supported formats:** `.txt`, `.py`, `.pdf` (pdfplumber → PyMuPDF fallback),
`.docx` (python-docx). Hard limits: max 10 MB per file, max 50 files per batch.

**NLP pipeline** (`plagcheck/src/preprocessor.py`): (1) lowercase, (2) strip
punctuation via regex, (3) NLTK word tokenization, (4) remove NLTK English
stopwords + `config/exclusions.txt`, (5) Porter stemming, (6) 5-gram sliding
window generation. Python source (`is_python=True`) is tokenized with the
`tokenize` module, not prose punctuation-stripping.

**The four similarity engines** (`plagcheck/src/models/`), one class per file
behind the `SimilarityModel` ABC in `base.py`:
1. `cosine.py` — TF-IDF cosine similarity via scikit-learn.
2. `winnowing.py` — SHA-256 rolling-hash fingerprinting (Schleimer et al.
   2003), `k=5`, `w=4`, Jaccard over fingerprint sets.
3. `jaccard.py` — Jaccard index over stemmed token sets.
4. `ast_model.py` — Python `ast` parser, identifier/function/class
   normalization, Levenshtein distance over `ast.dump()` node sequences.

`engine.py` orchestrates pairwise scans with `itertools.combinations`.

**Data layer** — PostgreSQL, 3NF, `plagcheck/db/schema.sql`: `app_user`,
`scan_request`, `scan_file`, `scan_pair`, `scan_algorithm`, `audit_log`.
`scan_request.scan_uuid` is the public API identifier; `scan_id` (SERIAL)
stays the internal PK. Every write goes through
`plagcheck/src/repository.py`, which falls back to JSON files under
`output/scans/` when PostgreSQL is unreachable — mirroring the audit
logger's file fallback in `plagcheck/src/audit.py`. The app must work fully
offline with no database running.

**Interfaces:** CLI (`plagcheck/plagcheck.py`, path-based) and Flask REST API
(`plagcheck/app.py`, multipart upload-based — never path-based, since a
browser can't send server paths and path input is a file-read vulnerability).

## Working rules

- Before advancing to the next phase of any multi-phase task: `ruff check`
  clean and `pytest` green (coverage ≥ 90% once Phase 4 is complete).
- Never leave stream-of-consciousness comments ("wait, actually...") in
  committed code — resolve the design decision, then write the clean result.
- Use `with open(...)` for all file I/O; no bare `open().write()`.
- Reuse `FileLoader`, `Preprocessor`, `AlgorithmEngine`, `ComparisonMatrix`,
  `ReportGenerator`, `AuditLogger` — do not duplicate their logic elsewhere.
- Frontend: TypeScript, no UI-kit dependency, CSS-variable design tokens in
  `web/src/styles/tokens.css`, `prefers-color-scheme` and
  `prefers-reduced-motion` both respected.
