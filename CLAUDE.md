# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

PlagCheck is a secure, local-execution plagiarism and file-similarity detection
system built for the CMSE 405 graduation project. It ships as a Python CLI
(`plagcheck/plagcheck.py`), a Flask REST API (`plagcheck/app.py`), and a React
web UI (`web/`).

## Commands

The virtualenv lives at `plagcheck/venv/` (both `pyrightconfig.json` and
`.vscode/settings.json` point at it). Run Python tooling from the **repo root**
via that interpreter — the ruff/pytest/coverage config is all in
`pyproject.toml`, which only resolves from the root:

```bash
plagcheck/venv/Scripts/python.exe -m pytest                      # full suite + coverage gate
plagcheck/venv/Scripts/python.exe -m pytest --no-cov             # skip the 90% gate while iterating
plagcheck/venv/Scripts/python.exe -m pytest tests/test_api.py -v # one file
plagcheck/venv/Scripts/python.exe -m pytest -k tc05              # one test by name
plagcheck/venv/Scripts/python.exe -m ruff check .                # lint (must be clean)
plagcheck/venv/Scripts/python.exe -m ruff check --fix .          # autofix
```

`pytest` enforces `--cov-fail-under=90`, so a green run means both tests and
coverage passed. Use `--no-cov` mid-change to avoid a red bar from coverage
alone. There is deliberately **no `pytest.ini`** — it would silently override
`[tool.pytest.ini_options]` in `pyproject.toml`.

CLI and API (run from inside `plagcheck/`, where `from src.…` imports resolve):

```bash
cd plagcheck
venv/Scripts/python.exe plagcheck.py --files ../samples/sample_a.txt ../samples/sample_b.txt \
    --algorithm all --threshold 0.5 --output ../output
venv/Scripts/python.exe app.py        # Flask on :5000
```

Frontend (from `web/`; Vite dev-proxies `/api` → `localhost:5000`, so run the
Flask app alongside it):

```bash
cd web
npm run dev      # :5173
npm run build    # tsc -b && vite build — must be clean
npm run lint     # oxlint
npx tsc -b       # typecheck only
```

## Architectural ground truth

Keep every change aligned with this. If a change would contradict it, stop
and flag the conflict instead of silently diverging.

**Supported formats:** `.txt`, `.py`, `.pdf` (pdfplumber → PyMuPDF fallback),
`.docx` (python-docx). Hard limits: max 10 MB per file, max 50 files per batch.

**NLP pipeline** (`plagcheck/src/preprocessor.py`): (1) lowercase, (2) strip
punctuation via regex, (3) NLTK word tokenization, (4) remove NLTK English
stopwords + `config/exclusions.txt`, (5) Porter stemming, (6) 5-gram sliding
window generation. Python source (`is_python=True`) is tokenized with the
`tokenize` module instead, falling back to the prose path when the source
fails to tokenize.

**The four similarity engines** (`plagcheck/src/models/`), one class per file
behind the `SimilarityModel` ABC in `base.py`:

1. `cosine.py` — TF-IDF cosine similarity via scikit-learn.
2. `winnowing.py` — SHA-256 rolling-hash fingerprinting (Schleimer et al.
   2003), `k=5`, `w=4`, Jaccard over fingerprint sets.
3. `jaccard.py` — Jaccard index over stemmed token sets.
4. `ast_model.py` — Python `ast` parser, identifier/function/class/attribute
   normalization, Levenshtein distance over `ast.dump()` output. Unlike the
   other three, it receives **raw source** (`[data["raw"]]`), not tokens —
   AST parsing needs the punctuation the NLP pipeline strips.

`engine.py` orchestrates pairwise scans with `itertools.combinations`. The
`"all"` algorithm is a **fixed weighted blend** (`_ALL_WEIGHTS`), not an
average: AST carries the largest share (0.40) for Python pairs because it is
the only rename-invariant signal, and is dropped entirely for non-Python
pairs with its weight redistributed across the text models. A plain average
would let the denominator silently shrink when AST is skipped, making scores
incomparable across a mixed batch — don't revert it to one.

**Data layer** — PostgreSQL, 3NF, `plagcheck/db/schema.sql`: `app_user`,
`scan_request`, `scan_file`, `scan_pair`, `scan_algorithm`, `audit_log`.
`scan_request.scan_uuid` is the public API identifier; `scan_id` (SERIAL)
stays the internal PK. Every write goes through
`plagcheck/src/repository.py`, which falls back to JSON files under
`output/scans/` when PostgreSQL is unreachable — mirroring the audit
logger's file fallback in `plagcheck/src/audit.py`. **The app must work fully
offline with no database running**, and the test suite must never require one.
Connections use `connect_timeout=2` so the offline path fails fast instead of
stalling every request on a TCP timeout.

**Interfaces:**

- CLI (`plagcheck/plagcheck.py`) is path-based and resolves each `--files`
  entry with `os.path.abspath()` *before* calling the loader. The loader
  rejects `..` as a path component (traversal defense for untrusted input),
  which would otherwise make ordinary relative paths like `../samples/a.txt`
  unusable from the CLI.
- Flask REST API (`plagcheck/app.py`) is **multipart upload-based, never
  path-based** — a browser cannot send server paths, and accepting them is a
  file-read vulnerability. Uploads land in a `tempfile.TemporaryDirectory()`
  sandbox that is always torn down. Endpoints: `GET /api/status`,
  `GET /api/algorithms`, `POST /api/check`,
  `GET /api/report/<scan_uuid>`, `GET /api/report/<scan_uuid>/pair/<a>/<b>`,
  `GET /api/report/<scan_uuid>/heatmap.png`. Errors use a
  `{error, code, detail}` envelope; the frontend switches on `code`.

Raw file text is **not** in the relational schema (it is working data, not a
durable record). `app.py` keeps it in a JSON sidecar next to the repository's
fallback files so the pair-comparison endpoint can rehydrate it.

## Frontend

`web/` is Vite + React + TypeScript with **no UI-kit dependency**. Design
tokens are CSS variables in `web/src/styles/tokens.css`; component styles in
`web/src/styles/app.css`. Both `prefers-color-scheme` and
`prefers-reduced-motion` are honored — keep new styling inside that token
system rather than hardcoding colors or durations.

- `src/api/client.ts` + `src/api/types.ts` — the only place that talks HTTP.
  `runCheck` uses `XMLHttpRequest` rather than `fetch` specifically to get
  `upload.onprogress` for the drop zone's progress bar.
- `src/hooks/useScan.ts` — holds all scan state as one discriminated union
  (`idle | uploading | processing | ready | error`), with a generation counter
  so a superseded request can't overwrite newer state. Prefer extending this
  union over adding parallel booleans.
- `HeatmapGrid` renders the matrix from JSON (not the server PNG) so cells are
  clickable; the PNG endpoint exists for report export.

Client-side validation in `DropZone` mirrors the server's limits (extensions,
10 MB, 50 files) — if you change a limit in `loader.py`, change it there too.

## Tests

`tests/` is the report's traceability matrix: test functions tagged
**TC-01 … TC-18** in their docstrings map to numbered test cases in the
graduation report. Keep those tags and their assertions intact; add new
coverage as separate untagged tests rather than repurposing a TC.

`tests/conftest.py` puts `plagcheck/` on `sys.path` so tests import as
`from src.… import …`, matching how the CLI and API run. API tests
monkeypatch `_get_connection` to `None` and redirect JSON storage into
`tmp_path`, so they never touch a real database or the repo's `output/`.

## Working rules

- Before advancing to the next phase of any multi-phase task: `ruff check`
  clean and `pytest` green.
- Never leave stream-of-consciousness comments ("wait, actually...") in
  committed code — resolve the design decision, then write the clean result.
- Use `with open(...)` for all file I/O; no bare `open().write()`.
- Reuse `FileLoader`, `Preprocessor`, `AlgorithmEngine`, `ComparisonMatrix`,
  `ReportGenerator`, `AuditLogger`, `ScanRepository` — do not duplicate their
  logic elsewhere.

## Design law (mirrored in `.cursorrules`)

1. **Taste** — clean, minimalist whitespace, muted pastel or monochrome
   high-contrast tones (Vercel style), elegant typography. Never cheap default
   colors or raw CSS grids without intent.
2. **Aesthetic interactions** — organic animations and state transitions on
   every frontend component, smooth easing curves.
3. **Impeccable execution** — pixel-perfection, 60 fps, explicit handling of
   loading states, error rollbacks, empty directories, and unsafe filenames.
4. **Vercel & Anthropic UI/UX** — monochrome design language, user-focused
   simplicity, no visual noise.
5. **Best practices** — modular, DRY, typed, clean code. Strict PEP 8 / PEP 257
   in Python; component-driven React with clean, minimal state.
