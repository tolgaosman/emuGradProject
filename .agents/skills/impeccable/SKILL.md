---
name: impeccable
description: >-
  Pixel-perfect, finished-feeling UI and clean code. Use when building or reviewing any frontend
  surface to ensure loading, error, empty, overflow and unsafe-input states are all handled.
---

# Impeccable — nothing half-finished

## The state matrix (every component that fetches or lists)
| State | Required behaviour |
|---|---|
| Loading | Skeleton or progress matching final layout size; no layout shift on arrival |
| Empty | Explain what belongs here and the one action to fill it |
| Error | Plain-language message, retry affordance, rollback of optimistic UI |
| Partial | Some files rejected: list each with its reason, keep the valid ones |
| Overflow | Long filenames truncate with a title; lists scroll, never grow the page |
| Offline API | Status pill shows unreachable; actions disabled with a reason, not silently failing |

## Project-specific cases
- Unsafe filenames: show a sanitized display name, never inject as HTML; preserve the original for download.
- Over 10 MB, over 50 files, wrong extension for the current mode: reject client-side with the same rules as the server.
- Expired or deleted scan reopened from history: error state with a way back, not a blank canvas.
- Threshold slider moves after a scan: flags re-derive client-side (`deriveResults`), no re-run.

## Visual precision
- Spacing from tokens only (`tokens.css`); 4px grid; no magic numbers.
- Align baselines and optical edges; icons share stroke weight and size scale (`components/icons.tsx`).
- Tabular numerals for scores and counts so columns do not jitter.
- Focus ring visible on every interactive element (amber, via token). Touch targets >= 36px.
- Check light, dark and reduced motion before calling it done.

## Code cleanliness
- Names describe intent; no `data2`, `temp`, `handleStuff`.
- No TODO/FIXME left behind, no commented-out code, no stream-of-consciousness comments.
- Files near 300 lines; split by responsibility.

## Review pass
Resize to 360px and 1440px, tab through with the keyboard, throttle the network, break the API, then drop a 12 MB file and a file named `<img src=x onerror=alert(1)>.txt`.
