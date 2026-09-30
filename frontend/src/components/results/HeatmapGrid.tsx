import { useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import { formatPercent } from '../../lib/format'
import { isFlagged } from '../../lib/risk'

interface HeatmapGridProps {
  names: string[]
  scores: number[][]
  threshold: number
  /** One-to-many shows only this row; a batch shows the upper triangle. */
  reference?: string
  onSelect: (fileA: string, fileB: string) => void
}

/** Intensity above which a cell's label switches to light text. */
const STRONG_INTENSITY = 0.55

export function HeatmapGrid({ names, scores, threshold, reference, onSelect }: HeatmapGridProps) {
  const [active, setActive] = useState<{ row: number; col: number } | null>(null)
  const gridRef = useRef<HTMLDivElement>(null)

  const rowIndices = reference ? [names.indexOf(reference)] : names.map((_, i) => i).slice(0, -1)
  const colIndices = reference
    ? names.map((_, i) => i).filter((i) => i !== rowIndices[0])
    : names.map((_, i) => i).slice(1)

  const isCell = (r: number, c: number) => (reference ? true : c > r)

  const focusCell = (rowPos: number, colPos: number) => {
    gridRef.current?.querySelector<HTMLButtonElement>(`[data-pos="${rowPos}-${colPos}"]`)?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent, rowPos: number, colPos: number) => {
    const moves: Record<string, [number, number]> = {
      ArrowRight: [0, 1],
      ArrowLeft: [0, -1],
      ArrowDown: [1, 0],
      ArrowUp: [-1, 0],
    }
    const move = moves[e.key]
    if (!move) return
    e.preventDefault()
    let r = rowPos + move[0]
    let c = colPos + move[1]
    // Skip over the empty lower triangle rather than stopping at it.
    while (r >= 0 && r < rowIndices.length && c >= 0 && c < colIndices.length) {
      if (isCell(rowIndices[r], colIndices[c])) {
        focusCell(r, c)
        return
      }
      r += move[0]
      c += move[1]
    }
  }

  return (
    <div className="heatmap-scroll">
      <div
        ref={gridRef}
        className="heatmap"
        role="grid"
        aria-label="Similarity matrix"
        style={{ '--cols': colIndices.length } as CSSProperties}
        onMouseLeave={() => setActive(null)}
      >
        <div className="heatmap-row" role="row">
          <span className="heatmap-corner" role="columnheader">
            <span className="visually-hidden">Document</span>
          </span>
          {colIndices.map((c) => (
            <span
              key={names[c]}
              role="columnheader"
              className="heatmap-col-label"
              data-active={active?.col === c || undefined}
              title={names[c]}
            >
              <span>{names[c]}</span>
            </span>
          ))}
        </div>

        {rowIndices.map((r, rowPos) => (
          <div key={names[r]} className="heatmap-row" role="row">
            <span
              role="rowheader"
              className="heatmap-row-label truncate"
              data-active={active?.row === r || undefined}
              title={names[r]}
            >
              {names[r]}
            </span>
            {colIndices.map((c, colPos) => {
              if (!isCell(r, c)) {
                return <span key={names[c]} role="gridcell" className="heatmap-cell heatmap-cell-empty" />
              }
              const score = scores[r]?.[c] ?? 0
              return (
                <span key={names[c]} role="gridcell">
                  <button
                    type="button"
                    className="heatmap-cell"
                    data-pos={`${rowPos}-${colPos}`}
                    data-flagged={isFlagged(score, threshold) || undefined}
                    data-strong={score >= STRONG_INTENSITY || undefined}
                    style={{ '--intensity': `${Math.round(score * 100)}%` } as CSSProperties}
                    tabIndex={rowPos === 0 && colPos === 0 ? 0 : -1}
                    aria-label={`${names[r]} and ${names[c]}: ${formatPercent(score)}`}
                    title={`${names[r]} ↔ ${names[c]} · ${formatPercent(score)}`}
                    onMouseEnter={() => setActive({ row: r, col: c })}
                    onFocus={() => setActive({ row: r, col: c })}
                    onBlur={() => setActive(null)}
                    onKeyDown={(e) => handleKeyDown(e, rowPos, colPos)}
                    onClick={() => onSelect(names[r], names[c])}
                  >
                    {Math.round(score * 100)}
                  </button>
                </span>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
