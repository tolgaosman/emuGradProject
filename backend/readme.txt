==============================================================================
 PlagCheck - Plagiarism & File Similarity Detection System (Quick Start)
==============================================================================

OVERVIEW
--------
Multi-algorithm plagiarism / source-code similarity detector.
Algorithms : cosine (TF-IDF), winnowing, jaccard, ast (Python).
Formats    : .txt, .pdf, .docx, .py, .java, .c, .h, .cpp, .cc, .hpp
Interfaces : command-line (plagcheck.py), Flask REST API (app.py),
             React web UI (../frontend).
Reports    : similarity_matrix.csv, comparison_report.html, similarity_heatmap.png


PREREQUISITES
-------------
- Python 3.12
- pip
- PostgreSQL is OPTIONAL. Without a database, scans and audit events fall
  back to local JSON/log files and the tool still runs normally.


INSTALLATION
------------
    cd backend
    python -m venv venv
    venv\Scripts\activate            (Windows)
    source venv/bin/activate         (macOS / Linux)
    pip install -r requirements.txt

NLTK data (English stopwords + punkt_tab) ships vendored in nltk_data/ and is
never downloaded — the app stays fully offline, including on first run.


CONFIGURATION
-------------
Settings live in backend/.env :
    APP_PORT=5000
    DB_HOST=localhost
    DB_NAME=plagcheck_db
    DB_USER=plagcheck_user
    DB_PASS=password
    DB_PORT=5432
    DEFAULT_THRESHOLD=0.70
    DEFAULT_MODE=text_similarity
    LOG_LEVEL=INFO
    RETENTION_DAYS=90

Academic exclusion list: config/exclusions.txt.
Override with --exclusions <path> or the EXCLUSIONS_PATH /
EXCLUSION_LIST_PATH env var.


CLI USAGE  (run from inside backend/)
--------------------------------------
    python plagcheck.py --files <file1> <file2> [more...] [options]

--files patterns are glob-expanded by the CLI itself, so docs/*.pdf works
even on Windows shells that don't expand wildcards.

Options:
    -f, --files        one or more file paths / globs (required)
    --mode              text_similarity | code_similarity  (default text_similarity)
    -a, --algorithm     cosine | winnowing | jaccard | ast | all      (default: none)
                        Forces a single model and, unless --mode is given, selects
                        its mode. Omit it (or pass 'all') for the default scoring,
                        which is matched-span coverage: the score equals the share
                        of the document the report highlights.
    --threshold         float 0.01 - 0.99                             (default 0.70)
    --min-match-words   ignore matches shorter than N words      (default 8, 0 off)
    --output            output directory                            (default output)
    --format            html | csv | both                             (default both)
    --exclusions        path to exclusion list      (default config/exclusions.txt)
    -q, --quiet         only print errors and flagged pairs
    --no-log            skip audit logging for this run
    --version           print the CLI version and exit

Exit status is 0 on a completed scan, 1 if no file could be loaded or an
argument was out of range.

Example:
    cp -r ../samples ./samples
    python plagcheck.py -f samples/sample_a.txt samples/sample_b.txt \
        --threshold 0.5

NOTE: the loader rejects paths containing '..' (path traversal). Pass files at
or below the current directory, or use absolute paths.


REST API USAGE  (run from inside backend/)
---------------------------------------------
    python app.py                 # http://localhost:$APP_PORT (default 5000)

    GET    /api/status                        health check + storage backend
    GET    /api/modes                         list scanning modes
    GET    /api/algorithms                    list algorithm choices per mode
    POST   /api/detect-language                guess a pasted snippet's language
    POST   /api/check                          run a comparison (multipart: files[],
                                               mode, algorithm, threshold,
                                               min_match_words)
    GET    /api/scans                          recent scans, newest first
    GET    /api/report/<scan_id>               retrieve a previous scan
    DELETE /api/report/<scan_id>               delete a scan and its stored text
    GET    /api/report/<scan_id>/pair/<a>/<b>
                                               both files' text + matched-span offsets
    GET    /api/report/<scan_id>/pair-pdf/<a>/<b>
                                               the same comparison as a downloadable PDF
                                               with the matched regions highlighted
    GET    /api/report/<scan_id>/matrix.csv    similarity matrix as CSV
    GET    /api/report/<scan_id>/report.html   full HTML comparison report
    GET    /api/report/<scan_id>/heatmap.png   300 DPI similarity heatmap

Errors always come back as {error, code, ...} JSON, including for
oversize/not-found/method-not-allowed requests.


OUTPUT ARTIFACTS  (in the output/ directory)
---------------------------------------------
    similarity_matrix.csv      full pairwise similarity matrix
    comparison_report.html     flagged-pair table with highlighted matches
    similarity_heatmap.png     annotated heatmap (flagged cells outlined red)

Persisted scan records and raw-text sidecars (output/scans/) are purged after
RETENTION_DAYS (default 90) and can be deleted on demand via the API or the
web UI's History panel.


TESTS  (run from inside backend/)
------------------------------------
    venv/Scripts/python.exe -m pytest -v
    venv/Scripts/python.exe -m pytest --cov=src
==============================================================================
