import type { SourceContribution } from '../api/types'

interface SimilarityIndexPanelProps {
  similarityIndices: Record<string, number>
  sourceBreakdowns: Record<string, SourceContribution[]>
  onSourceClick: (fileName: string, source: string, score: number) => void
}

function bandForIndex(index: number): 'low' | 'medium' | 'high' {
  if (index >= 0.5) return 'high'
  if (index >= 0.2) return 'medium'
  return 'low'
}

/** Turnitin-style per-document Similarity Index: "% of this document that
 * matched something else in the batch", ranked by source underneath. */
export function SimilarityIndexPanel({
  similarityIndices,
  sourceBreakdowns,
  onSourceClick,
}: SimilarityIndexPanelProps) {
  const files = Object.keys(similarityIndices)
  if (files.length === 0) return null

  const sorted = [...files].sort((a, b) => similarityIndices[b] - similarityIndices[a])

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Similarity Index</span>
      </div>

      <div className="similarity-index-list">
        {sorted.map((file) => {
          const index = similarityIndices[file]
          const percentage = Math.round(index * 100)
          const band = bandForIndex(index)
          const sources = sourceBreakdowns[file] ?? []

          return (
            <div key={file} className="similarity-index-row">
              <div className="similarity-index-row-head">
                <span className="file-name">{file}</span>
                <span className={`percentage-badge ${band}`}>{percentage}%</span>
              </div>
              <div className="progress-bar-bg">
                <div className={`progress-bar-fill ${band}`} style={{ width: `${percentage}%` }} />
              </div>
              {sources.length > 0 && (
                <ul className="similarity-index-sources">
                  {sources.map((s) => (
                    <li key={s.source}>
                      <button
                        type="button"
                        className="similarity-index-source-btn"
                        onClick={() => onSourceClick(file, s.source, s.contribution)}
                      >
                        <span>{s.source}</span>
                        <span>{Math.round(s.contribution * 100)}%</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
