import { motion } from 'motion/react'
import { useRef } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { spring } from '../lib/motion'

export interface SegmentedOption<T extends string> {
  value: T
  label: string
  icon?: ReactNode
}

interface SegmentedProps<T extends string> {
  /** Namespaces the sliding indicator's `layoutId`; unique per instance. */
  id: string
  label: string
  options: readonly SegmentedOption<T>[]
  value: T
  onChange: (value: T) => void
  disabled?: boolean
  size?: 'sm' | 'md'
  /** Hide option labels visually (icon-only), keeping them for screen readers. */
  iconOnly?: boolean
}

/** A radio-group segmented control. One tab stop; arrow keys move the
 * selection (roving tabindex), and the selected segment's background
 * glides between options on a spring. */
export function Segmented<T extends string>({
  id,
  label,
  options,
  value,
  onChange,
  disabled,
  size = 'md',
  iconOnly,
}: SegmentedProps<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const activeIndex = options.findIndex((o) => o.value === value)

  const handleKeyDown = (e: KeyboardEvent) => {
    if (disabled) return
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key]
    if (step === undefined) return
    e.preventDefault()
    const next = (activeIndex + step + options.length) % options.length
    onChange(options[next].value)
    refs.current[next]?.focus()
  }

  return (
    <div
      className={`segmented segmented-${size}`}
      role="radiogroup"
      aria-label={label}
      aria-disabled={disabled || undefined}
      onKeyDown={handleKeyDown}
    >
      {options.map((option, i) => {
        const selected = option.value === value
        return (
          <button
            key={option.value}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={iconOnly ? option.label : undefined}
            title={iconOnly ? option.label : undefined}
            tabIndex={selected ? 0 : -1}
            className="segmented-option"
            data-selected={selected || undefined}
            disabled={disabled}
            onClick={() => onChange(option.value)}
          >
            {selected && (
              <motion.span
                layoutId={`${id}-thumb`}
                className="segmented-thumb"
                transition={spring.snappy}
                aria-hidden="true"
              />
            )}
            <span className="segmented-content">
              {option.icon}
              {!iconOnly && option.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}
