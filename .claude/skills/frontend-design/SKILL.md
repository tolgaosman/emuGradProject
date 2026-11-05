---
name: frontend-design
description: >-
  Design and structure React/TypeScript UI for this app: layout, component boundaries, state shape,
  tokens, accessibility. Use when creating or restructuring any frontend feature.
---

# Frontend design — emuGradProject

## Architecture map
- `src/api/` the only HTTP layer (`client.ts`, `types.ts`). `runCheck` uses XHR for upload progress.
- `src/hooks/useScan.ts` single discriminated-union state machine (`idle | uploading | processing | loading | ready | error`).
- `src/lib/` pure logic: `deriveResults`, `risk`, `motion`.
- `src/components/` presentational and feature components; `DropZone/`, `results/`, `inspector/` are folders because they outgrew a file.
- `src/styles/` tokens plus per-area CSS (`base`, `layout`, `controls`, `results`, `overlays`).

## Building a feature
1. Write the state as a union before the JSX. Prefer extending `useScan`'s union to adding booleans.
2. Derive, don't store: anything computable from scan + threshold goes in `deriveResults`.
3. Components receive data and callbacks; they do not fetch. Fetching belongs to hooks calling `api/client`.
4. Put new CSS in the matching file under `styles/` using tokens. No inline colours.
5. Add types to `api/types.ts` first so the compiler guides the rest.

## Layout
Sticky `Header` + `WorkspaceTabs` (One vs many / Batch) over a two-column body: sticky sidebar (settings, dropzone) and a results canvas.
Collapse to one column below ~900px; the sidebar becomes a top section, never a hidden drawer for the primary action.

## Accessibility
- Semantic elements first (`button`, `nav`, `table`, or `role="grid"` with arrow-key navigation for the heatmap).
- Every control has an accessible name; icon-only buttons get `aria-label`.
- `aria-live="polite"` for scan progress and errors.
- Colour is never the only risk signal: pair it with a label or number.
- Respect `prefers-color-scheme` and `prefers-reduced-motion`.

## Quality gates
`npm run lint`, `npx tsc -b`, `npm run build` all clean. Keep files near 300 lines. No UI-kit dependency may be added.
