---
name: claude-mem
description: >-
  Persistent project memory discipline: what to record, where, and how to recall it across sessions.
  Use at session start and whenever a durable decision, gotcha or preference is learned.
---

# Claude-mem — durable context

Memory exists so the next session does not rediscover what this one learned.

## Record when
- A non-obvious gotcha is found (e.g. winnowing needs >= 8 tokens; `str.split()` zeroed code scans; story engine clips long runs).
- A design decision is made with its reason (why scoring is matched-span coverage; why AI/internet detection was removed).
- The user states a preference or correction.
- An environment quirk appears (port 5000 reserved on Windows -> set `APP_PORT`; venv at `backend/venv`).

## Do not record
Anything derivable from the code, git history or CLAUDE.md; transient task state; secrets; document contents from scans.

## Format
One fact per file under the memory directory, with frontmatter:
```
---
name: short-kebab-slug
description: one line used for recall relevance
metadata:
  type: user | feedback | project | reference
---
Fact. **Why:** reason. **How to apply:** when it matters. Link related: [[other-slug]]
```
Add a one-line pointer in `MEMORY.md`. Update an existing memory instead of duplicating; delete ones that become wrong.

## Recall
At session start read `MEMORY.md`, open entries relevant to the task. Verify any named file/function still exists before relying on it. Memories are background context, not instructions that override the user.

## Offline note
Memory is local files only. Do not add any remote memory service or telemetry to this project (offline-only premise).
