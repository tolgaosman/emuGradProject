---
name: awesome-design
description: >-
  Reference design language synthesized from well-regarded product UIs (Vercel, Linear, Anthropic, Stripe).
  Use when you need a concrete precedent for a pattern, then translate it into this project's tokens.
---

# Awesome design — precedents, translated

Do not copy a brand. Extract the principle and express it through `tokens.css`.

| Surface | Precedent principle | Apply here |
|---|---|---|
| Header | Vercel: slim, hairline bottom border, restrained nav | Sticky `Header`; brand left, mode switch centre, status/history/theme right |
| Tabs | Linear: text tabs with a sliding underline | `WorkspaceTabs` with a `layoutId` underline in amber |
| Dropzone | Stripe: dashed neutral border, clear hint, rich validation list | Rejected files listed with reasons, accepted ones kept |
| Tables | Linear/Vercel: dense rows, tabular numerals, row hover only | Results list sorted by score, mono numerals |
| Keyboard | Raycast/Vercel: keyboard-first | Arrow-key navigation on matrix and match navigator |
| Long text | Anthropic: warm neutrals, generous leading | Inspector text pane with line numbers, 1.6 leading |
| Status | Vercel deployments: small dot plus label | Status pill: green/amber/red dot with text |
| Compare | GitHub split diff | Two panes, muted highlights |

## Palette discipline
Neutral ramp (about 10 steps) in light and dark; one accent (amber); a muted semantic risk ramp (low/moderate/high/critical).
Never introduce a second accent hue.

## Process
1. Name the pattern needed ("filterable ranked list").
2. Recall two precedents and note the shared principle.
3. Implement with project tokens, springs and icons.
4. Compare against the table above for consistency.
