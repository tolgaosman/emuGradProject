---
name: framer-motion
description: >-
  Using the `motion` library (Framer Motion successor) in React 19: variants, AnimatePresence, layout
  animation, springs, gestures and reduced-motion handling. Use for any component-level animation code.
---

# Motion (Framer Motion) in this project

Package: `motion` — import from `motion/react`. Shared config lives in `src/lib/motion.ts`; reuse it, don't redefine.

## Core patterns
```tsx
<motion.div
  initial={{ opacity: 0, y: 6 }}
  animate={{ opacity: 1, y: 0 }}
  exit={{ opacity: 0 }}
  transition={spring.gentle}
/>
```
- **Mount/unmount:** wrap conditional children in `<AnimatePresence mode="popLayout">` with stable `key`s. Use `initial={false}` when children exist at first render.
- **Variants:** parent `staggerChildren` (0.02-0.04) for lists. Semantic names (`hidden`/`shown`).
- **Layout:** `layout` / `layoutId` for reordering and shared-element moves (e.g. the active tab underline). Avoid `layout` on large text blocks (scale distortion).
- **Gestures:** `whileTap={{ scale: 0.97 }}`; `whileHover` only on interactive rows.
- **Imperative:** `useAnimate` for sequences; `useMotionValue`/`useTransform` for scroll- or drag-linked values without re-renders.

## Rules
1. Animate `transform` and `opacity` only (x, y, scale, opacity). Never width/height/box-shadow.
2. Springs for interruptible or gesture motion; tween with token cubic-beziers for simple fades.
3. `MotionConfig reducedMotion="user"` is already in `main.tsx`; don't add manual overrides, but test with the OS setting on.
4. Keep animated components small; memoize heavy children so parent motion doesn't re-render lists (the matrix can be 50x50 cells).
5. Don't animate counts by re-rendering every frame; use `animate(motionValue)` with `useTransform`.
6. Guard `window` access in effects anyway.

## Pitfalls
- Exit animation not firing: the component is removed above `AnimatePresence`, or the key is missing/unstable.
- Layout jump in scrollable containers: add `layoutScroll` to the scroller.
- Flicker on first paint: set `initial` explicitly.

## Verify
`npm run build` and `npm run lint` clean; toggle reduced motion; throttle CPU 4x and confirm it still feels smooth.
