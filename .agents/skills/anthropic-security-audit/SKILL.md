---
name: anthropic-security-audit
description: >-
  Systematic security audit of the backend and frontend: untrusted uploads, path traversal, injection,
  data exposure, DoS limits, dependency risk. Use before releases or when touching loader, API or report code.
---

# Security audit

## Scope and threat model
Offline, local-execution tool. Untrusted input = uploaded files (names and content), URL params, JSON bodies.
Assets = uploaded documents, scan history, audit log. No outbound network calls are allowed in `backend/`.

## Audit steps
1. **Upload handling** (`app.py`, `loader.py`): sanitize names (`secure_filename`), allow-list extensions per mode, enforce 10 MB / 50 files, never trust `Content-Type`, reject `..` components, use the `TemporaryDirectory` sandbox and ensure teardown on every exit path.
2. **Parsers**: PDF (PyMuPDF), DOCX, `ast.parse` on uploaded code. Check for decompression bombs, huge page counts, deeply nested code (recursion). `ast.parse` never executes code; confirm nothing uses `eval`, `exec`, `pickle`, `yaml.load` or `subprocess(shell=True)`.
3. **Path-based access**: the API takes uploads only, never server paths. Report routes use `<uuid:...>`. Confirm file reads under `output/scans/` build paths from validated UUIDs.
4. **Injection**: SQL only via parameterized queries in `repository.py`. The HTML report and PDF export must escape filenames and document text before embedding in `<mark>` markup.
5. **Output and headers**: the error envelope hides stack traces; `Content-Disposition` filenames are sanitized; CORS is not a wildcard in production; consider `X-Content-Type-Options: nosniff`.
6. **DoS**: size limits, pair-count bound (50 files = 1225 pairs), regex backtracking in `language.py` signatures, retention purge works.
7. **Secrets and config**: DB credentials from env, none committed. `.gitignore` covers `output/`, venv, `.env.local`.
8. **Dependencies**: `pip list --outdated`, `pip-audit` if available, `npm audit` for the frontend.
9. **Frontend**: no `dangerouslySetInnerHTML` with document content; highlights rendered as React nodes. Downloads via blob with error handling.
10. **Audit log**: records actions, not document contents.

## Report format
`SEVERITY | file:line | issue | exploit scenario | fix`. Severities: Critical, High, Medium, Low, Info. Add a tests-to-add list; fixes land with a regression test.
