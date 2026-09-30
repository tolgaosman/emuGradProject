---
name: image-to-code
description: >-
  Best practices for converting UI mockups (images) into pixel-perfect, responsive code.
---

# Image to Pixel-Perfect Code

Translate visual designs into robust implementation accurately.

## Workflow
1. **Component Breakdown**: Before writing code, visually dissect the image into reusable components and layout wrappers (Flexbox/Grid).
2. **Token Extraction**: Identify the color palette, typography styles, and spacing rules from the image and set them up as CSS variables/Tailwind config first.
3. **Structural HTML**: Write the raw semantic HTML structure before applying any styling.
4. **Iterative Styling**: Apply styles from the outside in. Fix the main layout first, then focus on internal component details.
5. **Responsive Interpolation**: Since mockups are usually static (e.g., desktop only), intelligently infer and implement how the design should collapse on mobile devices.
