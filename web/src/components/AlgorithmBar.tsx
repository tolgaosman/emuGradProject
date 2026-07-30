import type { Algorithm } from '../api/types'

const LABELS: Record<Algorithm, string> = {
  cosine: 'Cosine',
  winnowing: 'Winnowing',
  jaccard: 'Jaccard',
  ast: 'AST',
  all: 'All',
}

interface AlgorithmBarProps {
  algorithms: Algorithm[]
  algorithm: Algorithm
  onAlgorithmChange: (algorithm: Algorithm) => void
  threshold: number
  onThresholdChange: (threshold: number) => void
  disabled?: boolean
}

export function AlgorithmBar({
  algorithms,
  algorithm,
  onAlgorithmChange,
  threshold,
  onThresholdChange,
  disabled,
}: AlgorithmBarProps) {
  return (
    <div className="algorithm-bar">
      <div className="algorithm-segmented" role="radiogroup" aria-label="Similarity algorithm">
        {algorithms.map((a) => (
          <button
            key={a}
            type="button"
            role="radio"
            aria-checked={a === algorithm}
            className={`segment${a === algorithm ? ' segment-active' : ''}`}
            disabled={disabled}
            onClick={() => onAlgorithmChange(a)}
          >
            {LABELS[a] ?? a}
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
