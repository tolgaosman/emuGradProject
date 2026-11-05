---
name: emil-kowalski
description: >-
  Emil Kowalski animation philosophy: fast, purposeful, interruptible micro-interactions using
  transform/opacity, custom easing and springs. Use whenever adding or tuning UI motion.
---

# Emil Kowalski — motion craft

## Decide whether to animate
Animate to explain a change (appearance, spatial origin, state), never to decorate. High-frequency actions
(typing, repeated clicks, keyboard navigation) get little or no animation.

## Timing
- Press feedback 100-160ms. Hover/colour 150ms. Popovers/menus 150-200ms. Modals/drawers 200-300ms. Never over 400ms for UI.
- Exits faster than enters (about 60-70%).
- Stagger list items 20-40ms, capping total stagger near 300ms.

## Easing
- Enter/exit: strong ease-out (`--ease-out`). On-screen movement: `--ease-in-out`. Drawers: `--ease-drawer`.
- Never `ease-in` for entrances, never `linear` except progress/time. Prefer springs (`spring.snappy`, `gentle`, `drawer` in `src/lib/motion.ts`) for gesture-driven or interruptible motion.

## Craft rules
1. Animate only `transform` and `opacity` (GPU, 60fps). Not width/height/top/left/box-shadow.
2. Never scale from 0; start from `scale(0.95)` plus opacity 0.
3. Origin-aware: popovers scale from their trigger, not the centre.
4. Buttons get `:active { transform: scale(0.97) }`.
5. Animations must be interruptible: CSS transitions or springs, not keyframes that restart.
6. Cards and containers do not animate on hover; only genuinely interactive rows do.
7. Blur/filter transitions only for tiny flourishes, never on large areas.

## Project wiring
- Import springs and easing from `src/lib/motion.ts`; do not inline cubic-beziers.
- `MotionConfig reducedMotion="user"` in `main.tsx` and the `prefers-reduced-motion` block in `tokens.css` must cover every new animation (opacity-only fallback, no movement).
- Use `AnimatePresence` for mount/unmount (results swap, inspector drawer, toasts); `initial={false}` on persistent lists.

## Review
Slow the animation 5x in devtools: does it still look right? Retrigger rapidly: does it glitch? Reduced motion on: does it still make sense?
