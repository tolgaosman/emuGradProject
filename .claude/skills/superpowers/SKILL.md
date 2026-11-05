---
name: superpowers
description: >-
  Disciplined engineering workflow: brainstorm, plan, test-first implementation, systematic debugging,
  verification before completion. Use for any multi-step feature or bug fix.
---

# Superpowers — workflow

## 1. Clarify (briefly)
Restate the goal and constraints. Ask only if the answer changes the work and cannot be inferred from code or CLAUDE.md.

## 2. Plan
Write a short numbered plan: files to touch, tests to add, order of steps, risks. Split into phases with a green gate between each (`ruff check` + `pytest`; frontend `tsc` + `build`).

## 3. Test-driven loop
1. Write a failing test that captures the behaviour (add untagged tests; never repurpose a TC-xx).
2. Run it and see it fail for the right reason.
3. Write the smallest implementation that passes.
4. Refactor with tests green.

## 4. Systematic debugging
Reproduce, isolate (bisect inputs or commits), form one hypothesis, test it with evidence (print, log, debugger), fix the root cause, add a regression test. Don't shotgun changes. After three failed hypotheses, re-read the code path end to end.

## 5. Verification before completion
Never say "done" without running tests, linter, build and (for UI) viewing the page. Report actual output. If something was skipped or is failing, say so.

## 6. Hygiene
Small commits with intent-revealing messages. Don't commit unless asked. No unrelated refactors in the same change. Leave no scratch files in the repo.

## Project gates
- `cd backend && venv/Scripts/python.exe -m pytest` (90% coverage gate) and `ruff check .`
- `cd frontend && npm run build && npm run lint`
