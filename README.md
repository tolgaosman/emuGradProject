# PlagCheck — Plagiarism & File Similarity Detection System

PlagCheck is a multi-algorithm plagiarism and source-code similarity detector.
It ingests documents, normalizes their text, compares every pair of files with one
or more similarity algorithms, and produces CSV / HTML / heatmap reports with the
suspicious pairs flagged.

## Features

- **Multiple algorithms** — TF-IDF **cosine** similarity, **winnowing** fingerprinting
  (Schleimer, Wilkerson & Aiken 2003), **Jaccard** index, and a normalized Python
  **AST** comparison that is robust to variable/function renaming.
- **Multiple formats** — `.txt`, `.py`, `.pdf` (pdfplumber with a PyMuPDF fallback),
  and `.docx`.
- **Two interfaces** — a command-line tool (`plagcheck.py`) and a Flask REST API (`app.py`).
- **Academic exclusion list** — `config/exclusions.txt` removes academic/template
  boilerplate (abstract, methodology, references, …) to reduce false positives.
- **Audit logging** — events are written to a PostgreSQL `audit_log` table, with an
  automatic fallback to a local `plagcheck.log` file when no database is available.
- **Reports** — `similarity_matrix.csv`, `comparison_report.html`, and a
  `similarity_heatmap.png` heatmap with flagged pairs highlighted in red.

## Prerequisites

- **Python 3.10+** (the code uses `int | None` and `list[str]` type syntax).
- `pip` for installing dependencies.
- **PostgreSQL is optional.** If a database is not reachable, audit events are written
  to `plagcheck/plagcheck.log` instead — the tool still runs normally.

## Installation

```bash
cd plagcheck
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

On first run the tool auto-downloads the required NLTK data sets (`punkt`,
`punkt_tab`, `stopwords`) if they are missing.

> **PDF note:** the report references `pypdf`; the implementation uses **pdfplumber**
> (with a **PyMuPDF** fallback) for more reliable text extraction. Both extract PDF text.

## Configuration

Configuration lives in `plagcheck/.env`:

| Key                 | Default          | Description                          |
| ------------------- | ---------------- | ------------------------------------ |
| `APP_PORT`          | `5000`           | Flask API port                       |
| `DB_HOST`           | `localhost`      | PostgreSQL host                      |
| `DB_NAME`           | `plagcheck_db`   | Database name                        |
| `DB_USER`           | `plagcheck_user` | Database user                        |
| `DB_PASS`           | `password`       | Database password                    |
| `DB_PORT`           | `5432`           | Database port                        |
| `DEFAULT_THRESHOLD` | `0.70`           | Similarity threshold for flagging    |
| `DEFAULT_ALGORITHM` | `cosine`         | Default algorithm                    |

**Exclusion list:** `config/exclusions.txt` (repo root) holds the academic/template
terms to ignore. Override the path with `--exclusions <path>` or the `EXCLUSIONS_PATH`
environment variable.

## CLI usage

Run from inside the `plagcheck/` directory:

```bash
python plagcheck.py --files <file1> <file2> [<file3> ...] [options]
```

| Flag           | Choices / type                          | Default            | Description                         |
| -------------- | --------------------------------------- | ------------------ | ----------------------------------- |
| `--files`      | one or more paths (required)            | —                  | Files to compare                    |
| `--algorithm`  | `cosine`, `winnowing`, `jaccard`, `ast`, `all` | `cosine`    | Similarity algorithm                |
| `--threshold`  | float `0.01`–`0.99`                     | `0.70`             | Flagging threshold                  |
| `--output`     | path                                    | `output`           | Report output directory             |
| `--format`     | `html`, `csv`, `both`                   | `both`             | Report format(s)                    |
| `--exclusions` | path                                    | `config/exclusions.txt` | Academic exclusion list       |

**Example:**

```bash
cd plagcheck
# Copy the sample files next to the run, then pass plain relative paths.
cp -r ../samples ./samples
python plagcheck.py --files samples/sample_a.txt samples/sample_b.txt \
    --algorithm all --threshold 0.5
```

This prints flagged pairs and writes `similarity_matrix.csv`,
`comparison_report.html`, and `similarity_heatmap.png` into `output/`.

> **Path note:** for safety, the loader rejects any path containing `..` (path
> traversal) and filenames with characters outside `A–Z a–z 0–9 . _ -`. Pass files
> that live at or below the current directory, or use absolute paths.

## REST API usage

Start the server from inside `plagcheck/`:

```bash
python app.py    # serves on http://localhost:5000
```

| Method | Endpoint               | Description                              |
| ------ | ---------------------- | ---------------------------------------- |
| GET    | `/api/status`          | Health check                             |
| GET    | `/api/algorithms`      | List supported algorithms                |
| POST   | `/api/check`           | Run a comparison                         |
| GET    | `/api/report/<scan_id>`| Retrieve a previous scan's flagged pairs |

**Example request:**

```bash
curl -X POST http://localhost:5000/api/check \
  -H "Content-Type: application/json" \
  -d '{"files": ["samples/sample_a.txt", "samples/sample_b.txt"],
       "algorithm": "cosine", "threshold": 0.5}'
```

**Example response:**

```json
{
  "scan_id": "f1e2...",
  "flagged": [
    {"file_a": "sample_a.txt", "file_b": "sample_b.txt", "score": 0.8123}
  ],
  "errors": []
}
```

## Output artifacts

Reports are written to the `--output` directory (default `output/`):

- `similarity_matrix.csv` — full pairwise similarity matrix.
- `comparison_report.html` — flagged-pair table (orange ≥ threshold, red ≥ 0.90).
- `similarity_heatmap.png` — annotated heatmap with flagged cells outlined in red.

## Running the tests

From the repository root:

```bash
pytest -v                 # run the full suite
pytest --cov=src          # run with coverage (requires pytest-cov)
```

The suite (`tests/`) covers the loader, preprocessor (including exclusion handling),
all four similarity models, the comparison matrix, the engine, the reporter, and the
audit-logger fallback. Tests run without a database or network connection.

## Project layout

```
emuGradProject/
├── config/
│   └── exclusions.txt          # academic exclusion list
├── output/                     # generated reports (.gitkeep tracked)
├── samples/                    # example documents for quick testing
├── tests/                      # pytest suite (TC-01 .. TC-18)
├── plagcheck/
│   ├── plagcheck.py            # CLI entry point
│   ├── app.py                  # Flask REST API
│   ├── readme.txt              # plain-text quick start
│   ├── requirements.txt
│   ├── db/schema.sql           # PostgreSQL schema (audit_log)
│   └── src/
│       ├── loader.py           # file ingestion + validation
│       ├── preprocessor.py     # tokenize / stopwords / exclusions / k-grams
│       ├── engine.py           # pairwise orchestration
│       ├── matrix.py           # similarity matrix + flagging + CSV
│       ├── reporter.py         # CSV / HTML / heatmap output
│       ├── audit.py            # audit logging (DB + file fallback)
│       └── models/             # cosine, winnowing, jaccard, ast
└── README.md
```
