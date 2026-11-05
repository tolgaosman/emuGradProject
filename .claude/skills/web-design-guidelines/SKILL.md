---
name: web-design-guidelines
description: >-
  Web interface review checklist (accessibility, performance, forms, focus, responsiveness, content).
  Use to audit UI code against concrete rules and report findings as file:line.
---

# Web interface guidelines — audit checklist

When asked to review UI, read the files, apply every rule below, and output findings as `path:line — issue — fix`.

## Accessibility
- Icon-only buttons have `aria-label`; form controls have `<label>` or `aria-label`.
- `<button>` for actions, `<a>` for navigation; no `div onClick`.
- Hierarchical headings, one `h1`. Landmarks: `header`, `main`, `nav`.
- Visible `:focus-visible` style; never `outline: none` without a replacement.
- Images have `alt` (empty if decorative). Contrast >= 4.5:1 body, 3:1 large text and UI.
- Async updates announced via `aria-live`.

## Forms
- Correct `type`, `inputmode` and `autocomplete`; don't block paste.
- Errors next to the field; focus the first invalid field on submit.
- Submit buttons show pending state and prevent double-submit.

## Interaction and motion
- `prefers-reduced-motion` honoured; animate `transform`/`opacity` only; no `transition: all`.
- Hit areas >= 36px (44px on touch); `touch-action: manipulation` on controls.
- Destructive actions confirm or are undoable.

## Layout and responsive
- Works from 360px to wide desktop; no horizontal page scroll.
- Long text: `text-overflow`, `min-width: 0` on flex children, `overflow-wrap` on filenames.
- `100dvh` not `100vh`; respect safe-area insets.

## Performance
- Large lists virtualized or paginated (50x50 matrix is the upper bound; keep cells light).
- Lazy-load heavy views; no layout shift (set dimensions); self-hosted fonts with `font-display: swap`.
- Memoize derived data; stable keys.

## Content
Concise, specific, sentence case, active voice; numbers with units; error text says how to fix.
