---
name: fine-skills
description: >-
  Use for precision engineering work: edge-case analysis, strict typing, explicit error
  handling, testable design. Apply before writing any non-trivial function, endpoint or hook.
---

# Fine Skills — precision engineering

## Workflow
1. **Enumerate inputs first.** Before the happy path, list: empty, single item, maximum size, wrong type,
   duplicate, unicode/unsafe filename, concurrent call, dependency unavailable.
2. **State the contract.** One sentence: what the function accepts, returns, raises. Encode it in types.
3. **Write the failure paths, then the success path.** Guard clauses over nested `if`.
4. **Test the edges you listed**, not just the happy path.

## Project edge-case checklist (this repo)
- Upload limits: 10 MB per file, 50 files per batch, extension allow-list per mode (`loader.py` + `DropZone/rules.ts` must agree).
- Single file is a valid scan (empty pair list); zero files is an error.
- Winnowing needs `>= k + w - 1` (8) tokens; shorter fixtures silently score 0.0.
- PostgreSQL may be down: every write goes through `ScanRepository` and must fall back to JSON.
- Malformed scan ids 404 via `<uuid:...>`; expired scans must surface as an error, never as an empty page.
- Paths: reject `..` components from untrusted input; the CLI resolves with `os.path.abspath()` first.

## Typing
- Python: full annotations, no bare `Any` except at a library boundary.
- TypeScript: no `any`; narrow instead of using non-null `!`. Prefer discriminated unions (see `useScan`).
- API payloads have one declared type in `src/api/types.ts`; never hand-roll shapes at call sites.

## Errors
- Never `except: pass` or an empty `catch {}`. Catch the narrowest exception, add context, re-raise or map to the `{error, code}` envelope.
- User-facing messages say what happened and what to do next; internal detail goes to the audit log.

## Design
- Small pure functions; side effects at the edges (I/O in repository/loader, logic in engine/reporter).
- Inject dependencies (preprocessor, repository) so tests can fake them.
- Reuse existing classes; do not copy their logic.

## Done means
`ruff check` clean, `pytest` green, `npm run build` clean, and each edge from step 1 has a test or an explicit reason it does not.
