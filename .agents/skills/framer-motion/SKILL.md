---
name: framer-motion
description: >-
  Detailed instructions on using Framer Motion effectively for layout animations, variants, 
  and performant UI transitions in React.
---

# Framer Motion Expertise

Bring UIs to life with performant, complex animations.

## Best Practices
1. **Layout Animations**: Use the `layout` prop for automatic transitions when elements change size or position. Use `layoutId` to animate between separate components.
2. **Variants**: Extract complex animation states into `variants` objects to keep JSX clean and allow for orchestrated parent-child animations.
3. **AnimatePresence**: Always use `<AnimatePresence>` to animate components out of the React tree when they are unmounted.
4. **Performance**: Animate transform (`translate`, `scale`, `rotate`) and `opacity` to avoid triggering layout recalculations (reflows).
5. **Accessibility**: Respect the user's motion preferences using the `useReducedMotion` hook to disable or minimize animations.
