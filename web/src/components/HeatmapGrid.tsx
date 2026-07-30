import type { CSSProperties } from 'react'

interface HeatmapGridProps {
  names: string[]
  scores: number[][]
  threshold: number
  onCellClick: (fileA: string, fileB: string, score: number) => void
}

export function HeatmapGrid({ names, scores, threshold, onCellClick }: HeatmapGridProps) {
  const n = names.length

  return (
    <div className="heatmap-scroll">
      <div
        className="heatmap-grid"
        style={{ '--heatmap-n': n } as CSSProperties}
        role="grid"
        aria-label="Similarity matrix"
      >
        <div className="heatmap-corner" aria-hidden="true" />
        {names.map((name) => (
          <div key={`col-${name}`} className="heatmap-col-label" title={name}>
            <span>{name}</span>
          </div>
        ))}

        {names.map((rowName, i) => (
          <div className="heatmap-row" key={`row-${rowName}`} role="row">
            <div className="heatmap-row-label" title={rowName}>
              {rowName}
            </div>
            {names.map((colName, j) => {
              const score = scores[i]?.[j] ?? 0
              const isDiagonal = i === j
              const flagged = !isDiagonal && score >= threshold
              const highConfidence = flagged && score >= 0.9
              return (
                <button
                  key={`cell-${rowName}-${colName}`}
                  type="button"
                  role="gridcell"
                  className={`heatmap-cell${flagged ? ' heatmap-cell-flagged' : ''}${
                    highConfidence ? ' heatmap-cell-high' : ''
                  }${isDiagonal ? ' heatmap-cell-diagonal' : ''}`}
                  style={{ '--intensity': isDiagonal ? 0 : score } as CSSProperties}
                  disabled={isDiagonal}
                  title={isDiagonal ? rowName : `${rowName} ↔ ${colName}: ${score.toFixed(4)}`}
                  onClick={() => !isDiagonal && onCellClick(rowName, colName, score)}
                >
                  <span className="heatmap-cell-score">{isDiagonal ? '—' : score.toFixed(2)}</span>
                </button>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
