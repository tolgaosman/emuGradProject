---
name: anti-slop
description: >-
  Remove generic AI boilerplate from code, copy and UI. Use when writing or reviewing anything to
  keep it intentional, minimal and specific to this project.
---

# Anti-slop

Every line must earn its place. If removing it changes nothing, remove it.

## Code smells to delete
- Comments that restate the code (`# increment counter`). Keep only *why* comments (non-obvious constraint, gotcha).
- Docstrings that repeat the signature. A PEP 257 one-liner stating purpose is enough.
- Abstractions with one caller: helper factories, wrapper classes, config objects for two constants.
- Defensive code for impossible states (null checks on values already validated upstream).
- Dead params, unused imports, speculative flags, "future-proof" hooks.
- Catch-all try/except that logs and continues.
- Padded names (`processDataAndReturnResultObject`).

## Copy and UI smells
- Filler: "Seamlessly", "powerful", "robust", "leverage", "Welcome to...", exclamation marks, emoji as icons.
- Three-card feature grids, gradient blobs, glassmorphism, default purple/blue accents.
- Generic empty states ("No data found"). Say what to do: "Drop two or more files to compare."
- Lorem ipsum or placeholder names in committed fixtures.

## Rules of thumb
1. Prefer deleting to adding. A diff that removes lines while fixing the bug is the best diff.
2. Match surrounding code: comment density, naming, idiom.
3. Reuse existing modules (`FileLoader`, `ScanEngine`, `ScanRepository`...) before writing parallel logic.
4. Do not reintroduce removed features: AI-generation detection, internet comparison, the blended cosine/winnowing score.
5. If a generated paragraph could appear in any project, rewrite it with a project-specific fact or cut it.

## Self-check before finishing
Read the diff as a hostile reviewer. For each added line ask: what breaks if this is gone? No answer means delete it.
