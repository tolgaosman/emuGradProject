import type { Transition } from 'motion/react'

/** Motion presets. Springs for anything that moves in space (indicators,
 * panels, lists); a strong ease-out for fades. Only transform and opacity
 * are ever animated. `MotionConfig reducedMotion="user"` in main.tsx turns
 * these into instant changes for users who ask for less motion. */
export const spring = {
  snappy: { type: 'spring', stiffness: 500, damping: 40, mass: 0.8 },
  gentle: { type: 'spring', stiffness: 260, damping: 30 },
  drawer: { type: 'spring', stiffness: 380, damping: 38, mass: 0.9 },
} satisfies Record<string, Transition>

export const EASE_OUT = [0.23, 1, 0.32, 1] as const

export const fade: Transition = { duration: 0.2, ease: EASE_OUT }

/** Enter/exit for panels that swap in place (results states, notices). */
export const panelMotion = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: 0.24, ease: EASE_OUT },
} as const
