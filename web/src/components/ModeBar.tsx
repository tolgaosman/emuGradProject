import type { Mode } from '../api/types'

const LABELS: Record<Mode, string> = {
  code_similarity: 'Code Similarity',
  text_similarity: 'Text Similarity',
  ai_code: 'AI Code Check',
  ai_text: 'AI Text Check',
}

interface ModeBarProps {
  modes: Mode[]
  mode: Mode
  onModeChange: (mode: Mode) => void
  threshold: number
  onThresholdChange: (threshold: number) => void
  disabled?: boolean
}

export function ModeBar({
  modes,
  mode,
  onModeChange,
  threshold,
  onThresholdChange,
  disabled,
}: ModeBarProps) {
  return (
    <div className="algorithm-bar">
      <div className="algorithm-segmented" role="radiogroup" aria-label="Scanning mode">
        {modes.map((m) => (
          <button
            key={m}
            type="button"
            role="radio"
            aria-checked={m === mode}
            className={`segment${m === mode ? ' segment-active' : ''}`}
            disabled={disabled}
            onClick={() => onModeChange(m)}
          >
            {LABELS[m] ?? m}
          </button>
        ))}
      </div>

      <div className="threshold-control">
        <label htmlFor="threshold-slider">
          Threshold <span className="threshold-value">{threshold.toFixed(2)}</span>
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
    </div>
  )
}
