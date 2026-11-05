---
name: taste
description: >-
  Visual taste for this project: monochrome-first, amber as the single accent, Geist typography,
  generous whitespace. Use for any layout, color, type or component styling decision.
---

# Taste

## Principles
- **Monochrome first.** Neutrals carry the interface. Amber (the logo colour) is reserved for the primary action,
  focus ring and active indicator. Nothing else is amber.
- **Whitespace is structure.** Group by proximity; use dividers sparingly; prefer 1px hairlines in `--border` tokens.
- **Typography does the hierarchy.** Geist for UI, Geist Mono for scores, filenames and code. Limit to 3-4 sizes and 2 weights per view.
- **Risk colour is semantic, not decorative.** Similarity bands come only from `src/lib/risk.ts`, muted not neon.

## Concrete rules
- Colours, radii, shadows, durations: CSS variables from `src/styles/tokens.css`. No hex literals in components.
- One radius family shared by inputs, buttons and cards.
- Shadows are rare and soft; elevation is mostly border + background step.
- Body text 14-15px, line-height 1.5; prose max ~70ch; tabular numerals.
- Icons only from `components/icons.tsx`, consistent stroke, `currentColor`. No emoji.
- One primary button per view. Secondary = outline/ghost. Destructive actions use a confirm step.
- Dark mode is a first-class theme, not an inversion: lower-contrast surfaces, desaturated accents.

## Anti-patterns
Default browser form controls, raw CSS grids with arbitrary gaps, rainbow charts, drop shadows on every card,
gradient buttons, centred paragraphs, ALL CAPS labels everywhere, tooltips for essential information.

## Check
Squint test: is there exactly one focal point? Remove the amber: does the hierarchy still read? If yes, ship.
