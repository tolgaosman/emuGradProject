---
name: image-to-code
description: >-
  Turn a screenshot or mockup into faithful React + CSS using the project's tokens and components.
  Use when the user supplies an image of a UI to implement or match.
---

# Image to code

## Procedure
1. **Inventory the image.** Read it (the Read tool renders images). List regions, repeating components, text styles, colours, spacing rhythm and the states shown.
2. **Map to the system.** For each element find the existing component or token: colours -> `tokens.css` variables (nearest match, flag deviations), icons -> `icons.tsx`, motion -> `lib/motion.ts`. Create a new component only if it is reused or exceeds ~60 lines.
3. **Measure.** Estimate spacing on the 4px grid, font sizes against the type scale, radii against the radius scale. Don't hardcode pixel values from the image when a token exists.
4. **Structure first.** Semantic HTML skeleton, then CSS in the matching `styles/*.css`, then behaviour.
5. **Cover unseen states.** The mock shows one state; implement loading, empty, error, hover, focus, disabled, dark mode and narrow width.
6. **Compare.** Run the dev server, screenshot it (see `playwright-cli`), put it beside the source, list remaining deltas, fix.

## Rules
- Never embed the screenshot as the UI. Never use absolute positioning to match pixels; use flex/grid.
- Text in the mock is placeholder: use real project copy.
- Respect the design law: monochrome + amber accent, no emoji icons, no UI kit.
- If the mock conflicts with CLAUDE.md (for example it shows an AI-detection score or a web-sources panel), flag it instead of building it.

## Output
Short summary: components created or changed, tokens added, deviations from the mock and why.
