---
name: task-observer
description: >-
  Keep multi-step work observable: explicit plan, progress tracking, regression watch, blocker reporting,
  scope control. Use on any task with more than ~3 steps or touching several modules.
---

# Task observer

## Track
- Break work into discrete, verifiable steps (use the todo/task tool, not a file committed to the repo).
- One step in progress at a time; mark done only after its check passes.
- Re-plan visibly when reality changes; don't silently skip steps.

## Phase gates (project rule)
Before starting the next phase: `ruff check` clean and `pytest` green (backend); `tsc -b`, `lint`, `build` clean (frontend). Record the gate result.

## Regression watch
After each change list what could be affected and check it:
| Changed | Re-check |
|---|---|
| `loader.py` limits | `DropZone/rules.ts`, TC upload tests |
| `reporter.matched_spans` / `min_match_words` | similarity index, pair endpoint, PDF export, highlight vs score parity |
| `preprocessor.py` | winnowing token minimums, language paths |
| API envelope/codes | `client.ts` error switch, `types.ts` |
| `risk.ts` | list, matrix, inspector, similarity index |

## Blockers
State the blocker, what was tried, and two options with a recommendation. Don't loop on the same failing approach more than twice.

## Scope control
If a request grows beyond the original ask (new feature, refactor, dependency), pause and surface it. Anything touching offline-only constraints (AI detection, external APIs) must be flagged before starting.

## Final report
Done / not done / skipped (with reason), commands run with real results, follow-ups. Short and factual.
