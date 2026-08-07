import { useState } from 'react'
import type { CSSProperties } from 'react'

interface HeatmapGridProps {
  referenceName: string
  candidateNames: string[]
  /** Reference-vs-candidate scores, aligned 1:1 with `candidateNames`. */
  scores: number[]
  threshold: number
  onCellClick: (candidateName: string, score: number) => void
}

/** Single-row heatmap: the reference file is the only row, each candidate
 * is a column — matches the reference/candidate upload model (there's
 * exactly one file to compare everything else against, not an N×N batch). */
export function HeatmapGrid({ referenceName, candidateNames, scores, threshold, onCellClick }: HeatmapGridProps) {
  const n = candidateNames.length
  const [hoveredCol, setHoveredCol] = useState<number | null>(null)

  return (
    <div className="heatmap-scroll">
      <div
        className="heatmap-grid heatmap-grid-single-row"
        style={{ '--heatmap-n': n } as CSSProperties}
        role="grid"
        aria-label="Similarity matrix"
        onMouseLeave={() => setHoveredCol(null)}
      >
        {/* Header cells need their own role="row" — as bare children of
            role="grid" the structure is invalid and screen readers can't
            associate a column with its label. */}
        <div className="heatmap-row" role="row">
          <div className="heatmap-corner" role="columnheader" aria-hidden="true" />
          {candidateNames.map((name, colIdx) => (
            <div
              key={`col-${name}`}
              role="columnheader"
              className={`heatmap-col-label${hoveredCol === colIdx ? ' heatmap-label-active' : ''}`}
              title={name}
            >
              <span>{name}</span>
            </div>
          ))}
        </div>

        <div className="heatmap-row" role="row">
          <div
            className="heatmap-row-label heatmap-row-label-reference"
            role="rowheader"
            title={referenceName}
          >
            {referenceName}
          </div>
          {candidateNames.map((name, j) => {
            const score = scores[j] ?? 0
            const flagged = score >= threshold
            const highConfidence = flagged && score >= 0.9
            const isHovered = hoveredCol === j
            return (
              <button
                key={`cell-${name}`}
                type="button"
                role="gridcell"
                className={`heatmap-cell${flagged ? ' heatmap-cell-flagged' : ''}${
                  highConfidence ? ' heatmap-cell-high' : ''
                }${isHovered ? ' heatmap-cell-hovered' : ''}`}
                style={{ '--intensity': score } as CSSProperties}
                title={`${referenceName} ↔ ${name}: ${score.toFixed(4)}`}
                onMouseEnter={() => setHoveredCol(j)}
                onFocus={() => setHoveredCol(j)}
                onClick={() => onCellClick(name, score)}
              >
                <span className="heatmap-cell-score">{score.toFixed(2)}</span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
