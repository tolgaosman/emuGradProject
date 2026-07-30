import { useEffect, useState } from 'react'
import { getAlgorithms } from '../api/client'
import type { Algorithm, Mode } from '../api/types'

const ALGORITHM_LABELS: Record<Algorithm, string> = {
  auto: 'All Blended',
  cosine: 'Cosine',
  winnowing: 'Winnowing',
  jaccard: 'Jaccard',
  ast: 'AST',
}

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

/** The mockup's ALGORITHM + THRESHOLD card. Chips are an advanced override
 * on top of the mode's designed blend ("All Blended" / auto) — omitted
 * entirely for AI modes, where none of this has meaning. */
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
  const [choices, setChoices] = useState<Algorithm[]>(['auto'])

  useEffect(() => {
    const fallback: Algorithm[] =
      mode === 'code_similarity'
        ? ['auto', 'ast', 'winnowing', 'jaccard']
        : ['auto', 'cosine', 'winnowing', 'jaccard']
    getAlgorithms()
      .then((res) => setChoices(res.by_mode[mode] ?? fallback))
      .catch(() => setChoices(fallback))
  }, [mode])

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Algorithm</span>
      </div>

      <div className="chip-row" role="radiogroup" aria-label="Algorithm override">
        {choices.map((choice) => (
          <button
            key={choice}
            type="button"
            role="radio"
            aria-checked={choice === algorithm}
            className={`chip${choice === algorithm ? ' chip-active' : ''}`}
            disabled={disabled}
            onClick={() => onAlgorithmChange(choice)}
          >
            {ALGORITHM_LABELS[choice]}
          </button>
        ))}
      </div>

      <div className="settings-slider">
        <label htmlFor="threshold-slider">
          <span>Threshold</span>
          <span className="settings-slider-value">{threshold.toFixed(2)}</span>
        </label>
        <input
          id="threshold-slider"
          type="range"
          min={0.05}
          max={0.99}
          step={0.01}
          value={threshold}
          disabled={disabled}
          onChange={(e) => onThresholdChange(Number(e.target.value))}
        />
      </div>

      <div className="settings-slider">
        <label htmlFor="min-match-words-slider">
          <span>Min match words</span>
          <span className="settings-slider-value">{minMatchWords}</span>
        </label>
        <input
          id="min-match-words-slider"
          type="range"
          min={1}
          max={25}
          step={1}
          value={minMatchWords}
          disabled={disabled}
          onChange={(e) => onMinMatchWordsChange(Number(e.target.value))}
        />
        <p className="settings-slider-hint">Ignore matches shorter than this many words.</p>
      </div>
    </div>
  )
}
