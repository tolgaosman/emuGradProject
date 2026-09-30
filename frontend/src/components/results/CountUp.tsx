import { animate, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { EASE_OUT } from '../../lib/motion'

interface CountUpProps {
  value: number
  format: (value: number) => string
}

/** Counts up to `value` once when it first appears (and on change), rather
 * than popping in — skipped entirely for reduced-motion users. */
export function CountUp({ value, format }: CountUpProps) {
  const reduceMotion = useReducedMotion()
  const [display, setDisplay] = useState(reduceMotion ? value : 0)

  useEffect(() => {
    if (reduceMotion) {
      setDisplay(value)
      return
    }
    const controls = animate(0, value, { duration: 0.7, ease: EASE_OUT, onUpdate: setDisplay })
    return () => controls.stop()
  }, [value, reduceMotion])

  return (
    <span className="num">
      <span aria-hidden="true">{format(display)}</span>
      <span className="visually-hidden">{format(value)}</span>
    </span>
  )
}
