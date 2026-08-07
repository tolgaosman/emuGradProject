# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

PlagCheck is a secure, local-execution plagiarism and file-similarity detection
system built for the CMSE 405 graduation project. It ships as a Python CLI
(`plagcheck/plagcheck.py`), a Flask REST API (`plagcheck/app.py`), and a React
web UI (`web/`). **It is intentionally offline-only** — file-vs-file similarity
comparison, nothing more. There is no AI-generation detection and no internet/
external-API comparison anywhere in the system; both were built and then
deliberately removed to keep the project aligned with its local-execution
premise. Don't reintroduce either without being explicitly asked.

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
    --mode text_similarity --threshold 0.5 --output ../output
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

**Two user-facing modes, not four algorithms directly:** `text_similarity`
and `code_similarity` (`plagcheck/src/language.py`'s `MODES`). Both score by
matched-span coverage by default (see below); the `algorithm` parameter
(`auto` | `cosine` | `winnowing` | `jaccard` | `ast`) lets a caller force a
single raw model instead, for demoing/reviewing each one individually.
`text_similarity` accepts `.txt`/`.pdf`/`.docx`; `code_similarity`
accepts `.py`/`.java`/`.c`/`.h`/`.cpp`/`.cc`/`.hpp`. Hard limits: max 10 MB per
file, max 50 files per batch. A single uploaded file is a valid scan — it just
produces an empty pair list (no artificial 2-file minimum).

**NLP pipeline** (`plagcheck/src/preprocessor.py`): (1) lowercase, (2) strip
punctuation via regex, (3) NLTK word tokenization, (4) remove NLTK English
stopwords + `config/exclusions.txt`, (5) Porter stemming, (6) 5-gram sliding
window generation. Python source (`language="python"`) is tokenized with the
`tokenize` module instead; Java/C/C++ (`language in {"java","c","cpp"}`) use a
generic regex tokenizer (`language.strip_comments_and_strings` +
identifier/number extraction) since Python's `tokenize` module only
understands Python syntax. Both code paths fall back to the prose path if
tokenizing fails.

**The four similarity engines** (`plagcheck/src/models/`), one class per file
behind the `SimilarityModel` ABC in `base.py`:

1. `cosine.py` — TF-IDF cosine similarity via scikit-learn.
2. `winnowing.py` — SHA-256 rolling-hash fingerprinting (Schleimer et al.
   2003), `k=5`, `w=4`, Jaccard over fingerprint sets. Needs `>= k + w - 1`
   (8) tokens to produce any fingerprint at all — fewer and it silently
   returns 0.0; a real gotcha worth remembering when writing fixtures.
3. `jaccard.py` — Jaccard index over stemmed token sets.
4. `ast_model.py` — Python `ast` parser, identifier/function/class/attribute
   normalization, Levenshtein distance over `ast.dump()` output. Unlike the
   other three, it receives **raw source** (`[data["raw"]]`), not tokens —
   AST parsing needs the punctuation the NLP pipeline strips. Only applies to
   Python; Java/C/C++ pairs fall back to winnowing alone.

**Scoring is matched-span coverage, not a model score.** With
`algorithm="auto"` (the default for both modes) `ScanEngine.compute()` scores
a pair as `max(coverage_a, coverage_b)` where coverage is the fraction of
that document's characters falling inside `reporter.matched_spans()` — the
exact ranges the comparison view highlights. The score is therefore, by
construction, "how much of this document is highlighted", and can never rise
from something there is nothing to show for. `max` rather than mean so a
short document copied wholesale into a long one still reads ~100%.

This replaced an earlier `0.5·cosine + 0.5·winnowing` (and `0.7·AST +
0.3·winnowing`) blend, and then a winnowing-only pass. Don't reintroduce
either: cosine scores whole-document vocabulary overlap and winnowing
*samples* k-grams (it keeps roughly a quarter of them and needs `>= k+w-1`
tokens to emit anything), so both disagree with the highlighting — winnowing
scored the demo fixtures at 2.6% while the report highlighted 43.6%.

`matched_spans()` counts two kinds of evidence, both highlightable:
shared literal 5-grams, and — for Python-to-Python pairs — whole
functions/classes whose *normalized* ASTs match (`reporter._structural_spans`,
reusing `ast_model._NormalizerNodeVisitor`). The second exists because
renaming every identifier defeats literal matching completely; it is what
keeps `samples/sample_code_b.py` (a pure rename of `sample_code_a.py`)
scoring ~79% instead of ~8%, with each matched function highlighted.

`ScanEngine.compute()` also computes a Turnitin-style per-document
**Similarity Index** and ranked **source breakdown** (`similarity_index.py`)
— all three come from one `similarity_index.compute_all()` pass that runs
span matching once per unordered pair, so the matrix, the index and the
breakdown can't disagree, and the expensive step isn't repeated. The index is
the asymmetric "% of this document matched something else," distinct from the
symmetric pairwise matrix. Without a `preprocessor` the index/breakdown are
skipped and `auto` degrades to winnowing — a library/test path only; both
real callers always pass one.

`min_match_words` (Turnitin's "exclude matches smaller than N words",
default 8) filters spans *before* any of it. It counts `\w+` runs, not
`str.split()` chunks: whitespace splitting treats `def add(a,b):` as one
word, which silently zeroed every code scan. The same filter must be applied
anywhere spans are shown — `/api/report/<uuid>/pair/...` and
`reporter._render_pairs` both take it, defaulting to the value the scan was
run with (persisted in the JSON text sidecar), so highlighting can never
exceed what the score counted. The PDF export shares that filtering via
`app._pair_payload`, which both pair endpoints call, so the on-screen
inspector and the downloaded PDF cannot highlight different things.

**PDF export** (`ReportGenerator.pair_pdf_bytes`) renders one comparison —
both documents in full, stacked, with the matched spans marked — via
`fitz.Story` + `fitz.DocumentWriter` entirely in memory, like
`heatmap_png_bytes`. PyMuPDF is already a dependency (the PDF *loader*), so
this adds none. Two constraints to keep in mind: MuPDF's story engine
*clips* rather than wraps an unbroken run wider than the line box, which is
why `_wrap_segments` hard-wraps at `_PDF_WRAP_COLS` before rendering (it
wraps the highlight segments, not the raw text, so `<mark>` boundaries stay
put); and the header's score/threshold/mode come from
`repository.get_scan()`, never from query parameters, so a link can't make
the PDF state a score the scan never produced.

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
  unusable from the CLI. `--algorithm` is a legacy alias for `--mode` (maps
  `ast`→`code_similarity`, everything else→`text_similarity`).
- Flask REST API (`plagcheck/app.py`) is **multipart upload-based, never
  path-based** — a browser cannot send server paths, and accepting them is a
  file-read vulnerability. Uploads land in a `tempfile.TemporaryDirectory()`
  sandbox that is always torn down. Endpoints: `GET /api/status`,
  `GET /api/modes`, `GET /api/algorithms`, `POST /api/detect-language`,
  `POST /api/check`, `GET /api/report/<scan_uuid>`,
  `GET /api/report/<scan_uuid>/pair/<a>/<b>`,
  `GET /api/report/<scan_uuid>/pair-pdf/<a>/<b>`,
  `GET /api/report/<scan_uuid>/heatmap.png`. Errors use a
  `{error, code, detail}` envelope; the frontend switches on `code`.
  `/api/detect-language` is a small offline heuristic (regex signature
  scoring in `language.py`) for the code paste-box UI — not AI-generation
  detection, just "is this Python/Java/C/C++."

Raw file text is **not** in the relational schema (it is working data, not a
durable record). `app.py` keeps it in a JSON sidecar next to the repository's
fallback files so the pair-comparison endpoint can rehydrate it.

## Frontend

`web/` is Vite + React + TypeScript with **no UI-kit dependency**. Design
tokens are CSS variables in `web/src/styles/tokens.css`; component styles in
`web/src/styles/app.css`. Both `prefers-color-scheme` and
`prefers-reduced-motion` are honored — keep new styling inside that token
system rather than hardcoding colors or durations. Layout is a fixed
`Sidebar` (mode picker: Text/Code groups, each with one "Similarity Check"
entry) plus a two-column content area (`ScanSettings`/`DropZone` on the left,
results on the right).

- `src/api/client.ts` + `src/api/types.ts` — the only place that talks HTTP.
  `runCheck` uses `XMLHttpRequest` rather than `fetch` specifically to get
  `upload.onprogress` for the drop zone's progress bar.
- `src/hooks/useScan.ts` — holds all scan state as one discriminated union
  (`idle | uploading | processing | ready | error`), with a generation counter
  so a superseded request can't overwrite newer state. Prefer extending this
  union over adding parallel booleans.
- `HeatmapGrid` renders the matrix from JSON (not the server PNG) so cells are
  clickable; the PNG endpoint exists for report export. `CodePane` is the
  shared line-numbered/span-highlighted source renderer used by the inline
  `ComparisonInspector` card.

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
- Reuse `FileLoader`, `Preprocessor`, `ScanEngine`, `ComparisonMatrix`,
  `ReportGenerator`, `AuditLogger`, `ScanRepository` — do not duplicate their
  logic elsewhere.
- No outbound network calls anywhere in `plagcheck/` — this was tried once
  (an internet-source-comparison feature via a paid search API) and reverted
  because it broke the local-execution premise the project is built on. Any
  future request to add AI-generation detection or external API calls should
  be flagged back to the user before starting, not built silently.

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
