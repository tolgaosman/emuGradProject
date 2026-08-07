import { pairPdfUrl } from '../api/client'
import { DownloadIcon } from './icons'

interface SimilarityReportProps {
  scanId: string
  referenceName: string
  names: string[]
  scores: number[][]
  threshold: number
  minMatchWords: number
  onSelectPair: (fileA: string, fileB: string, score: number) => void
}

/** Strip the extension so the suggested download name stays readable. The
 * server's Content-Disposition is authoritative; this is only a hint. */
function stem(name: string) {
  const dot = name.lastIndexOf('.')
  return dot > 0 ? name.slice(0, dot) : name
}

/** Per-candidate similarity report: each uploaded "check" file scored
 * directly against the single reference file, ranked highest first —
 * distinct from the full N×N matrix above it. Each row can be opened in the
 * inspector or downloaded as a highlighted PDF. */
export function SimilarityReport({
  scanId,
  referenceName,
  names,
  scores,
  threshold,
  minMatchWords,
  onSelectPair,
}: SimilarityReportProps) {
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
              <div className="similarity-report-row">
                <button
                  type="button"
                  className="similarity-report-row-main"
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
                    <div
                      className={`progress-bar-fill ${state}`}
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                </button>

                <a
                  className="icon-btn"
                  href={pairPdfUrl(scanId, referenceName, row.name, minMatchWords)}
                  download={`${stem(referenceName)} vs ${stem(row.name)}.pdf`}
                  title="Download this comparison as a highlighted PDF"
                  aria-label={`Download the highlighted PDF comparing ${referenceName} with ${row.name}`}
                >
                  <DownloadIcon />
                </a>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
