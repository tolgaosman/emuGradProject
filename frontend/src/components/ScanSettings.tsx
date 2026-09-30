import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import { getAlgorithms } from '../api/client'
import type { Algorithm, Mode } from '../api/types'
import { ALGORITHM_HINT, ALGORITHM_LABEL, formatPercent } from '../lib/format'
import { EASE_OUT } from '../lib/motion'
import { ChevronIcon } from './icons'

const FALLBACK_CHOICES: Record<Mode, Algorithm[]> = {
  text_similarity: ['auto', 'cosine', 'winnowing', 'jaccard'],
  code_similarity: ['auto', 'ast', 'winnowing', 'jaccard'],
}
const THRESHOLD_TICKS = [0.5, 0.7, 0.9]

interface ScanSettingsProps {
  mode: Mode
  algorithm: Algorithm
  onAlgorithmChange: (algorithm: Algorithm) => void
  threshold: number
  onThresholdChange: (threshold: number) => void
  minMatchWords: number
  onMinMatchWordsChange: (words: number) => void
  disabled?: boolean
}

export function ScanSettings({
  mode,
  algorithm,
  onAlgorithmChange,
  threshold,
  onThresholdChange,
  minMatchWords,
  onMinMatchWordsChange,
  disabled,
}: ScanSettingsProps) {
  const [choices, setChoices] = useState<Algorithm[]>(FALLBACK_CHOICES[mode])
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const chipRefs = useRef<(HTMLButtonElement | null)[]>([])
  const uid = useId()

  useEffect(() => {
    let cancelled = false
    setChoices(FALLBACK_CHOICES[mode])
    getAlgorithms()
      .then((res) => {
        if (!cancelled && res.by_mode[mode]) setChoices(res.by_mode[mode])
      })
      .catch(() => {
        // The fallback list already matches the server's.
      })
    return () => {
      cancelled = true
    }
  }, [mode])

  const handleChipKeys = (e: KeyboardEvent) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key]
    if (step === undefined || disabled) return
    e.preventDefault()
    const current = choices.indexOf(algorithm)
    const next = (current + step + choices.length) % choices.length
    onAlgorithmChange(choices[next])
    chipRefs.current[next]?.focus()
  }

  return (
    <div className="settings">
      <div className="field">
        <div className="field-row">
          <label htmlFor={`${uid}-threshold`} className="field-label">
            Flag for review at
          </label>
          <output htmlFor={`${uid}-threshold`} className="field-value num">
            {formatPercent(threshold)}
          </output>
        </div>
        <input
          id={`${uid}-threshold`}
          className="range"
          type="range"
          min={0.05}
          max={0.99}
          step={0.01}
          value={threshold}
          disabled={disabled}
          aria-valuetext={`${formatPercent(threshold)} similarity`}
          style={{ '--fill': `${((threshold - 0.05) / 0.94) * 100}%` } as CSSProperties}
          onChange={(e) => onThresholdChange(Number(e.target.value))}
        />
        <div className="range-ticks" aria-hidden="true">
          {THRESHOLD_TICKS.map((tick) => (
            <button
              key={tick}
              type="button"
              tabIndex={-1}
              className="range-tick"
              style={{ left: `${((tick - 0.05) / 0.94) * 100}%` }}
              disabled={disabled}
              onClick={() => onThresholdChange(tick)}
            >
              {formatPercent(tick)}
            </button>
          ))}
        </div>
      </div>

      <button
        type="button"
        className="disclosure"
        aria-expanded={advancedOpen}
        aria-controls={`${uid}-advanced`}
        onClick={() => setAdvancedOpen((open) => !open)}
      >
        <span>Advanced</span>
        <span className="disclosure-summary">
          {ALGORITHM_LABEL[algorithm]} · {minMatchWords}-word minimum
        </span>
        <motion.span animate={{ rotate: advancedOpen ? 180 : 0 }} transition={{ duration: 0.2, ease: EASE_OUT }}>
          <ChevronIcon size={14} />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {advancedOpen && (
          <motion.div
            id={`${uid}-advanced`}
            className="advanced"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.26, ease: EASE_OUT }}
          >
            <div className="advanced-inner">
              <div className="field">
                <span className="field-label" id={`${uid}-algorithm`}>
                  Scoring
                </span>
                <div
                  className="chips"
                  role="radiogroup"
                  aria-labelledby={`${uid}-algorithm`}
                  onKeyDown={handleChipKeys}
                >
                  {choices.map((choice, i) => (
                    <button
                      key={choice}
                      ref={(el) => {
                        chipRefs.current[i] = el
                      }}
                      type="button"
                      role="radio"
                      aria-checked={choice === algorithm}
                      tabIndex={choice === algorithm ? 0 : -1}
                      className="chip"
                      disabled={disabled}
                      onClick={() => onAlgorithmChange(choice)}
                    >
                      {ALGORITHM_LABEL[choice]}
                      {choice === 'auto' && <span className="chip-tag">Default</span>}
                    </button>
                  ))}
                </div>
                <p className="field-hint">{ALGORITHM_HINT[algorithm]}</p>
              </div>

              <div className="field">
                <div className="field-row">
                  <label htmlFor={`${uid}-words`} className="field-label">
                    Ignore matches shorter than
                  </label>
                  <output htmlFor={`${uid}-words`} className="field-value num">
                    {minMatchWords} {minMatchWords === 1 ? 'word' : 'words'}
                  </output>
                </div>
                <input
                  id={`${uid}-words`}
                  className="range"
                  type="range"
                  min={1}
                  max={25}
                  step={1}
                  value={minMatchWords}
                  disabled={disabled}
                  aria-valuetext={`${minMatchWords} words`}
                  style={{ '--fill': `${((minMatchWords - 1) / 24) * 100}%` } as CSSProperties}
                  onChange={(e) => onMinMatchWordsChange(Number(e.target.value))}
                />
                <p className="field-hint">Short common phrases stop counting as evidence.</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
