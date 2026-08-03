interface SimilarityReportProps {
  referenceName: string
  names: string[]
  scores: number[][]
  threshold: number
  onSelectPair: (fileA: string, fileB: string, score: number) => void
}

/** Per-candidate similarity report: each uploaded "check" file scored
 * directly against the single reference file, ranked highest first —
 * distinct from the full N×N matrix above it. */
export function SimilarityReport({ referenceName, names, scores, threshold, onSelectPair }: SimilarityReportProps) {
  const refIdx = names.indexOf(referenceName)
  if (refIdx === -1) return null

  const rows = names
    .map((name, i) => ({ name, score: scores[refIdx]?.[i] ?? 0 }))
    .filter((row) => row.name !== referenceName)
    .sort((a, b) => b.score - a.score)

  if (rows.length === 0) return null

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Similarity Report</span>
        <span className="similarity-report-subtitle">vs {referenceName}</span>
      </div>

      <ul className="similarity-report-list">
        {rows.map((row) => {
          const percentage = Math.round(row.score * 100)
          const flagged = row.score >= threshold
          const state = flagged ? 'high' : 'low'

          return (
            <li key={row.name}>
              <button
                type="button"
                className="similarity-report-row"
                onClick={() => onSelectPair(referenceName, row.name, row.score)}
              >
                <div className="similarity-report-row-head">
                  <span className="file-name">{row.name}</span>
                  <span className="similarity-report-row-right">
                    {flagged && (
                      <span className="similarity-report-flag" role="img" aria-label="Flagged">
                        🚩
                      </span>
                    )}
                    <span className={`similarity-index-percentage ${state}`}>{percentage}%</span>
                  </span>
                </div>
                <div className="progress-bar-bg">
                  <div className={`progress-bar-fill ${state}`} style={{ width: `${percentage}%` }} />
                </div>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
