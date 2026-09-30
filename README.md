# PlagCheck — Plagiarism & File Similarity Detection System

PlagCheck is a **local-execution** plagiarism and file-similarity detector, built
for the CMSE 405 graduation project. It ingests documents or source files,
normalizes their text, compares every pair with one or more similarity
algorithms, and produces CSV / HTML / PDF / heatmap reports with the matching
passages highlighted. No document ever leaves the machine it runs on — there
is no AI-generation detection and no internet/external-API comparison
anywhere in the system.

## Features

- **Two scanning modes** — `text_similarity` (`.txt`, `.pdf`, `.docx`) and
  `code_similarity` (`.py`, `.java`, `.c`, `.h`, `.cpp`, `.cc`, `.hpp`).
- **Four similarity algorithms** — TF-IDF **cosine** similarity, **winnowing**
  fingerprinting (Schleimer, Wilkerson & Aiken 2003), **Jaccard** index, and a
  normalized Python **AST** comparison that is robust to variable/function
  renaming. The default score (`auto`) is matched-span coverage — the same
  evidence the comparison view highlights — rather than a single raw model.
- **Two workflows in the web UI** — check one document against many, or a
  full class batch, all-vs-all.
- **Academic exclusion list** — `backend/config/exclusions.txt` removes
  academic/template boilerplate (abstract, methodology, references, …) from
  prose comparisons to reduce false positives.
- **Similarity Index** — a Turnitin-style "% of this document found
  elsewhere," with a ranked source breakdown, alongside the pairwise matrix.
- **Audit logging** — events are written to a PostgreSQL `audit_log` table,
  with an automatic fallback to a local log file when no database is
  available.
- **Reports** — CSV matrix, self-contained HTML report, 300 DPI heatmap PNG,
  and a per-pair highlighted PDF export.
- **Three interfaces** — a command-line tool (`plagcheck.py`), a Flask REST
  API (`app.py`), and a React web UI (`frontend/`).

## Prerequisites

- **Python 3.12**.
- `pip` for installing dependencies.
- **Node.js 20+** and `npm`, for the web UI.
- **PostgreSQL is optional.** If a database is not reachable, scans and audit
  events fall back to local JSON/log files — the tool still runs normally.

## Installation

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

NLTK data (English stopwords + `punkt_tab`) ships vendored in
`backend/nltk_data/` and is loaded from there — nothing is downloaded, on
first run or ever.

> **PDF note:** the report references `pypdf`; the implementation uses
> **pdfplumber** (with a **PyMuPDF** fallback) for more reliable text
> extraction. Both extract PDF text.

## Configuration

Configuration lives in `backend/.env`:

| Key                 | Default            | Description                            |
| -------------------- | ------------------- | --------------------------------------- |
| `APP_PORT`           | `5000`              | Flask API port                          |
| `DB_HOST`            | `localhost`         | PostgreSQL host                         |
| `DB_NAME`            | `plagcheck_db`      | Database name                           |
| `DB_USER`            | `plagcheck_user`    | Database user                           |
| `DB_PASS`            | —                   | Database password                       |
| `DB_PORT`            | `5432`              | Database port                           |
| `DEFAULT_THRESHOLD`  | `0.70`              | Similarity threshold for flagging       |
| `DEFAULT_MODE`       | `text_similarity`   | Default scanning mode                   |
| `LOG_LEVEL`          | `INFO`              | Python logging level                    |
| `RETENTION_DAYS`     | `90`                | How long scans/text sidecars are kept   |

**Exclusion list:** `backend/config/exclusions.txt` holds the academic/
template terms to ignore. Override the path with `--exclusions <path>` or
the `EXCLUSIONS_PATH` / `EXCLUSION_LIST_PATH` environment variable.

## CLI usage

Run from inside `backend/`:

```bash
python plagcheck.py --files <file1> <file2> [<file3> ...] [options]
```

`--files` accepts glob patterns (e.g. `docs/*.pdf`) — expanded by the CLI
itself so this works even on Windows shells that don't expand wildcards.

| Flag                | Choices / type                                 | Default                  | Description                               |
| -------------------- | ----------------------------------------------- | ------------------------- | ------------------------------------------ |
| `-f`, `--files`      | one or more paths/globs (required)              | —                          | Files to compare                           |
| `--mode`             | `text_similarity`, `code_similarity`            | `text_similarity`          | Scanning mode                              |
| `-a`, `--algorithm`  | `cosine`, `winnowing`, `jaccard`, `ast`, `all`  | none (matched-span coverage) | Force a single model                    |
| `--threshold`        | float `0.01`–`0.99`                             | `0.70`                     | Flagging threshold                         |
| `--min-match-words`  | int                                              | `8`                         | Ignore matches shorter than N words (0 disables) |
| `--output`           | path                                             | `output`                    | Report output directory                    |
| `--format`           | `html`, `csv`, `both`                           | `both`                      | Report format(s)                           |
| `--exclusions`       | path                                             | `config/exclusions.txt`     | Academic exclusion list                    |
| `-q`, `--quiet`      | flag                                             | off                         | Only print errors and flagged pairs        |
| `--no-log`           | flag                                             | off                         | Skip audit logging for this run            |
| `--version`          | flag                                             | —                           | Print the CLI version and exit             |

**Example:**

```bash
cd backend
# Copy the sample files next to the run, then pass plain relative paths.
cp -r ../samples ./samples
python plagcheck.py -f samples/sample_a.txt samples/sample_b.txt --threshold 0.5
```

This prints flagged pairs and writes `similarity_matrix.csv`,
`comparison_report.html`, and `similarity_heatmap.png` into `output/`.

> **Path note:** for safety, the loader rejects any path containing `..`
> (path traversal) and filenames with characters outside
> `A–Z a–z 0–9 . _ -`. Pass files that live at or below the current
> directory, or use absolute paths.

## REST API usage

Start the server from inside `backend/`:

```bash
python app.py    # serves on http://localhost:$APP_PORT (default 5000)
```

| Method   | Endpoint                              | Description                                |
| -------- | -------------------------------------- | -------------------------------------------- |
| `GET`    | `/api/status`                         | Health check + storage backend               |
| `GET`    | `/api/modes`                          | List scanning modes                          |
| `GET`    | `/api/algorithms`                     | List algorithm choices per mode              |
| `POST`   | `/api/detect-language`                | Guess a pasted snippet's language            |
| `POST`   | `/api/check`                          | Run a comparison (`multipart/form-data`)     |
| `GET`    | `/api/scans`                          | Recent scans, newest first                   |
| `GET`    | `/api/report/<scan_id>`               | Retrieve a previous scan                     |
| `DELETE` | `/api/report/<scan_id>`               | Delete a scan and its stored text            |
| `GET`    | `/api/report/<scan_id>/pair/<a>/<b>`  | Both files' text + matched-span offsets      |
| `GET`    | `/api/report/<scan_id>/pair-pdf/<a>/<b>` | Highlighted PDF of one comparison         |
| `GET`    | `/api/report/<scan_id>/matrix.csv`    | Similarity matrix as CSV                     |
| `GET`    | `/api/report/<scan_id>/report.html`   | Full HTML comparison report                  |
| `GET`    | `/api/report/<scan_id>/heatmap.png`   | 300 DPI similarity heatmap                   |

`/api/check` takes uploaded files, never server paths — a browser can't send
paths, and accepting them would be a file-read vulnerability. Errors always
come back as `{error, code, ...}` JSON.

**Example request:**

```bash
curl -X POST http://localhost:5000/api/check \
  -F "files=@samples/sample_a.txt" \
  -F "files=@samples/sample_b.txt" \
  -F "mode=text_similarity" \
  -F "threshold=0.5"
```

**Example response (trimmed):**

```json
{
  "scan_id": "f1e2...",
  "mode": "text_similarity",
  "threshold": 0.5,
  "pairs": [
    {"file_a": "sample_a.txt", "file_b": "sample_b.txt", "score": 0.81, "flagged": true, "matched_kgrams": 12}
  ],
  "summary": {"pair_count": 1, "flagged_count": 1, "max_score": 0.81, "mean_score": 0.81},
  "errors": []
}
```

## Web UI

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /api to the Flask server
```

Run the Flask API (`python backend/app.py`) alongside it. The UI offers two
workspaces — **One vs many** (a reference document checked against
candidates) and **Batch · class** (every submission against every other) —
plus a comparison inspector with side-by-side highlighted matches, a scan
history drawer, and CSV/HTML/PDF/PNG export.

## Output artifacts

Reports are written to the `--output` directory (default `output/`):

- `similarity_matrix.csv` — full pairwise similarity matrix.
- `comparison_report.html` — flagged-pair table with highlighted matches.
- `similarity_heatmap.png` — annotated heatmap with flagged cells outlined in red.

Persisted scan records and their raw-text sidecars (`output/scans/`) are
purged after `RETENTION_DAYS` (default 90) and can be deleted on demand via
the API or the web UI's History panel.

## Running the tests

From inside `backend/`:

```bash
venv/Scripts/python.exe -m pytest -v          # run the full suite
venv/Scripts/python.exe -m pytest --cov=src   # run with coverage
```

The suite (`backend/tests/`) covers the loader, preprocessor (including
exclusion handling and the offline NLTK fallback), all four similarity
models, the comparison matrix, the engine, the reporter, the repository
(including history/retention), and the audit-logger fallback. Tests run
without a database or network connection.

## Project layout

```
emuGradProject/
├── documents/                  # project report, proposal, screenshots
├── frontend/                   # React + TypeScript web UI (Vite)
│   └── src/
│       ├── api/                 # HTTP client + response types
│       ├── components/          # DropZone/, results/, inspector/, ...
│       ├── hooks/                # useScan, useTheme, useApiStatus, ...
│       ├── lib/                  # risk bands, formatting, motion presets
│       └── styles/               # design tokens + area-split stylesheets
└── backend/
    ├── plagcheck.py             # CLI entry point
    ├── app.py                   # Flask REST API
    ├── readme.txt               # plain-text quick start
    ├── requirements.txt
    ├── nltk_data/                # vendored NLTK data (offline)
    ├── config/exclusions.txt    # academic exclusion list
    ├── samples/                 # example documents for quick testing
    ├── tests/                   # pytest suite (TC-01 .. TC-18 + untagged)
    ├── db/schema.sql            # PostgreSQL schema
    └── src/
        ├── loader.py             # file ingestion + validation
        ├── preprocessor.py       # tokenize / stopwords / exclusions / k-grams
        ├── engine.py             # pairwise orchestration
        ├── matrix.py             # similarity matrix + flagging + CSV
        ├── similarity_index.py   # matched spans, Similarity Index, source breakdown
        ├── reporter.py           # CSV / HTML / heatmap / PDF output
        ├── repository.py         # persistence (PostgreSQL + JSON fallback)
        ├── audit.py              # audit logging (DB + file fallback)
        ├── db.py                 # shared PostgreSQL connection helper
        └── models/               # cosine, winnowing, jaccard, ast
```
