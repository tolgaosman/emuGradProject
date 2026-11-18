import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import { getAlgorithms, getExclusions } from '../api/client'
import type { Algorithm, Mode } from '../api/types'
import { ALGORITHM_HINT, ALGORITHM_LABEL, formatPercent } from '../lib/format'
import { EASE_OUT } from '../lib/motion'
import { DEFAULT_MIN_MATCH_WORDS } from './DropZone/rules'
import { ChevronIcon, CloseIcon } from './icons'

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
  excludedTerms: string[]
  onExcludedTermsChange: (terms: string[]) => void
  useDefaultExclusions: boolean
  onUseDefaultExclusionsChange: (enabled: boolean) => void
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
  excludedTerms,
  onExcludedTermsChange,
  useDefaultExclusions,
  onUseDefaultExclusionsChange,
  disabled,
}: ScanSettingsProps) {
  const [byMode, setByMode] = useState<Partial<Record<Mode, Algorithm[]>>>({})
  const [defaultTerms, setDefaultTerms] = useState<string[] | null>(null)
  const [showDefaultTerms, setShowDefaultTerms] = useState(false)
  const [termDraft, setTermDraft] = useState('')
  const [advancedToggle, setAdvancedToggle] = useState<boolean | null>(null)

  const choices = byMode[mode] ?? FALLBACK_CHOICES[mode]
  const hasCustomExclusions = excludedTerms.length > 0 || !useDefaultExclusions
  const advancedOpen =
    advancedToggle ?? (algorithm !== 'auto' || minMatchWords !== DEFAULT_MIN_MATCH_WORDS || hasCustomExclusions)

  const chipRefs = useRef<(HTMLButtonElement | null)[]>([])
  const uid = useId()

  useEffect(() => {
    let cancelled = false
    getAlgorithms()
      .then((res) => {
        if (!cancelled) setByMode(res.by_mode)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const toggleDefaultListPreview = () => {
    const next = !showDefaultTerms
    setShowDefaultTerms(next)
    if (next && defaultTerms === null) {
      getExclusions()
        .then((res) => setDefaultTerms(res.terms))
        .catch(() => setDefaultTerms([]))
    }
  }

  const commitDraftTerms = (raw: string) => {
    const incoming = raw
      .split(/[,\n;]+/)
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean)
    if (incoming.length === 0) return
    const merged = Array.from(new Set([...excludedTerms, ...incoming])).slice(0, 100)
    onExcludedTermsChange(merged)
    setTermDraft('')
  }

  const removeCustomTerm = (term: string) => {
    onExcludedTermsChange(excludedTerms.filter((t) => t !== term))
  }

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
        onClick={() => setAdvancedToggle(!advancedOpen)}
      >
        <span>Advanced & exclusions</span>
        <span className="disclosure-summary">
          {ALGORITHM_LABEL[algorithm]} · {minMatchWords}w min
          {excludedTerms.length > 0 ? ` · +${excludedTerms.length} excl` : ''}
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
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2, ease: EASE_OUT }}
          >
            <div className="advanced-inner">
              <div className="field">
                <span className="field-label" id={`${uid}-algorithm`}>
                  Scoring engine
                </span>
                <div className="chips" role="radiogroup" aria-labelledby={`${uid}-algorithm`} onKeyDown={handleChipKeys}>
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
                <p className="field-hint">Filters out short incidental phrases from scoring and highlights.</p>
              </div>

              {mode === 'text_similarity' && (
                <div className="field exclusion-box">
                  <div className="field-row">
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={useDefaultExclusions}
                        disabled={disabled}
                        onChange={(e) => onUseDefaultExclusionsChange(e.target.checked)}
                      />
                      <span className="field-label">Academic boilerplate filter</span>
                    </label>
                    <button type="button" className="btn btn-link" onClick={toggleDefaultListPreview}>
                      {showDefaultTerms ? 'Hide terms' : 'View 50 terms'}
                    </button>
                  </div>
                  {showDefaultTerms && (
                    <div className="term-cloud" aria-label="Default academic exclusions">
                      {defaultTerms === null ? (
                        <span className="field-hint">Loading terms…</span>
                      ) : (
                        defaultTerms.map((term) => (
                          <span key={term} className="term-pill">
                            {term}
                          </span>
                        ))
                      )}
                    </div>
                  )}

                  <label htmlFor={`${uid}-excl`} className="field-label exclusion-sub">
                    Custom excluded terms
                  </label>
                  <div className="exclusion-input-row">
                    <input
                      id={`${uid}-excl`}
                      type="text"
                      className="text-input"
                      placeholder="e.g. cmse405, eastern mediterranean"
                      value={termDraft}
                      disabled={disabled}
                      onChange={(e) => setTermDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ',') {
                          e.preventDefault()
                          commitDraftTerms(termDraft)
                        }
                      }}
                      onBlur={() => {
                        if (termDraft.trim()) commitDraftTerms(termDraft)
                      }}
                    />
                  </div>
                  {excludedTerms.length > 0 && (
                    <div className="term-cloud">
                      {excludedTerms.map((term) => (
                        <span key={term} className="term-pill term-pill-custom">
                          {term}
                          <button
                            type="button"
                            className="term-pill-remove"
                            aria-label={`Remove excluded term ${term}`}
                            disabled={disabled}
                            onClick={() => removeCustomTerm(term)}
                          >
                            <CloseIcon size={11} />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
