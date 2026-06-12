==============================================================================
 PlagCheck - Plagiarism & File Similarity Detection System (Quick Start)
==============================================================================

OVERVIEW
--------
Multi-algorithm plagiarism / source-code similarity detector.
Algorithms : cosine (TF-IDF), winnowing, jaccard, ast (Python).
Formats    : .txt, .py, .pdf, .docx
Interfaces : command-line (plagcheck.py) and Flask REST API (app.py).
Reports    : similarity_matrix.csv, comparison_report.html, similarity_heatmap.png


PREREQUISITES
-------------
- Python 3.10 or newer
- pip
- PostgreSQL is OPTIONAL. Without a database, audit events are written to
  plagcheck.log instead and the tool still runs normally.


INSTALLATION
------------
    cd plagcheck
    python -m venv venv
    venv\Scripts\activate            (Windows)
    source venv/bin/activate         (macOS / Linux)
    pip install -r requirements.txt

On first run, the required NLTK data (punkt, punkt_tab, stopwords) is
downloaded automatically if missing.


CONFIGURATION
-------------
Settings live in plagcheck/.env :
    APP_PORT=5000
    DB_HOST=localhost
    DB_NAME=plagcheck_db
    DB_USER=plagcheck_user
    DB_PASS=password
    DB_PORT=5432
    DEFAULT_THRESHOLD=0.70
    DEFAULT_ALGORITHM=cosine

Academic exclusion list: config/exclusions.txt  (repo root).
Override with --exclusions <path> or the EXCLUSIONS_PATH env var.


CLI USAGE  (run from inside plagcheck/)
---------------------------------------
    python plagcheck.py --files <file1> <file2> [more...] [options]

Options:
    --files       one or more file paths (required)
    --algorithm   cosine | winnowing | jaccard | ast | all   (default cosine)
    --threshold   float 0.01 - 0.99                            (default 0.70)
    --output      output directory                             (default output)
    --format      html | csv | both                            (default both)
    --exclusions  path to exclusion list   (default config/exclusions.txt)

Example:
    cp -r ../samples ./samples
    python plagcheck.py --files samples/sample_a.txt samples/sample_b.txt \
        --algorithm all --threshold 0.5

NOTE: the loader rejects paths containing '..' (path traversal). Pass files at
or below the current directory, or use absolute paths.


REST API USAGE  (run from inside plagcheck/)
--------------------------------------------
    python app.py                 # http://localhost:5000

    GET  /api/status              health check
    GET  /api/algorithms          list supported algorithms
    POST /api/check               run a comparison (JSON body: files, algorithm, threshold)
    GET  /api/report/<scan_id>    retrieve a previous scan's flagged pairs


OUTPUT ARTIFACTS  (in the output/ directory)
--------------------------------------------
    similarity_matrix.csv      full pairwise similarity matrix
    comparison_report.html     flagged-pair table
    similarity_heatmap.png     annotated heatmap (flagged cells outlined red)


TESTS  (run from the repository root)
-------------------------------------
    pytest -v
    pytest --cov=src
==============================================================================
