---
name: code-review
description: >-
  Structured code review: correctness first, then security, tests, design, style. Use when asked to review
  a diff, branch or PR, or before declaring a task done.
---

# Code review

## Order of attack
1. **Understand intent.** Read the commit message or PR description and the touched tests. What should be true after this change?
2. **Correctness.** Trace each changed path with concrete inputs: empty, boundary, error. Check off-by-one, None/undefined, async races, stale state (the generation counter in `useScan`), and exception paths that leak temp files.
3. **CLAUDE.md compliance.** Offline-only; no AI detection; scoring is matched-span coverage (no blended models); `min_match_words` applied wherever spans are shown; uploads not paths; limits mirrored in `loader.py` and `DropZone/rules.ts`; errors in the `{error, code}` envelope.
4. **Security.** See `security-guidance`: escaping, traversal, injection, limits.
5. **Tests.** New behaviour has a test. TC-01..TC-18 tagged tests are untouched. Tests need no DB and never touch the real `output/`.
6. **Design.** Reuses existing classes? File near 300 lines? Smallest abstraction that works? Dead code?
7. **Style.** ruff clean, PEP 8/257, types; frontend tokens, motion rules, no inline colours, accessibility.

## Running checks
```
cd backend && venv/Scripts/python.exe -m ruff check . && venv/Scripts/python.exe -m pytest
cd frontend && npx tsc -b && npm run lint && npm run build
```

## Output format
Group by severity: **Blocker** (wrong or insecure), **Should fix**, **Nit**. Each item: `file:line`, what is wrong, a concrete failing scenario, suggested fix. Lead with a one-line verdict. Don't pad with praise or restate the diff. Report only issues you can justify; say plainly when nothing was found.
