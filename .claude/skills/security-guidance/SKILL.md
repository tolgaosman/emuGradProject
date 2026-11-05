---
name: security-guidance
description: >-
  Secure-coding rules to follow while writing code (not after). Use whenever handling files, user input,
  SQL, subprocesses, HTML output or secrets in this repo.
---

# Security guidance — while coding

## Always
- Validate at the boundary, early: type, size, extension, count, charset. Fail closed with the `{error, code}` envelope.
- Treat filenames as data: `secure_filename` for storage, `html.escape` or React text nodes for display.
- Parameterize SQL. Never string-format queries.
- Use `tempfile.TemporaryDirectory()` for uploads; clean up on every exit path.
- Resolve a path, then verify it stays inside the intended root.
- Keep secrets in environment variables; never log them or document text.
- Keep dependencies minimal; no new network-capable libraries in `backend/`.

## Never
- `eval`, `exec`, `pickle.loads`, `yaml.load`, `shell=True`, `os.system` on anything derived from input.
- Accept server file paths from API clients.
- `dangerouslySetInnerHTML`, `innerHTML` or `document.write` with scan or document content.
- Return exception messages or stack traces to clients.
- Disable TLS/CORS/CSRF protections "temporarily".
- Add outbound calls (search APIs, telemetry, AI detection). Flag any such request to the user first.

## Patterns
```python
dest = (root / secure_filename(name)).resolve()
if not dest.is_relative_to(root.resolve()):
    raise ValueError("Invalid file name")
```
```tsx
<span>{doc.name}</span>   {/* text node, never HTML injection */}
```

## Review triggers
Any change to `loader.py`, `app.py` routes, `repository.py`, `reporter.py` HTML/PDF output, or `client.ts` download code deserves a security pass and a regression test.
