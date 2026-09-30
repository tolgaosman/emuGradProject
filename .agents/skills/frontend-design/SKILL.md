---
name: frontend-design
description: >-
  Use this for comprehensive guidance on building modern frontend applications, 
  emphasizing responsive design, accessibility, and modern frameworks.
---

# Frontend Design Masterclass

Build modern, resilient, and performant frontend applications.

## Principles
1. **Responsive First**: Always use fluid layouts (`rem`, `vh`, `vw`, `%`, `clamp()`) and mobile-first media queries.
2. **Accessibility (a11y)**: Semantic HTML is mandatory. Use `aria-` attributes only when semantic tags fall short. Ensure sufficient color contrast.
3. **CSS Architecture**: Use CSS Variables (Custom Properties) extensively for theming. Avoid deep nesting in CSS/SCSS.
4. **State Management**: Keep state as close to where it's needed as possible. Avoid global state unless absolutely necessary.
5. **Performance**: Lazy load non-critical resources. Optimize images (WebP/AVIF) and minimize main-thread blocking JavaScript.
