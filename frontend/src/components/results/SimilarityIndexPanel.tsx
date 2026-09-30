import { motion } from 'motion/react'
import type { SourceContribution } from '../../api/types'
import { formatPercent } from '../../lib/format'
import { spring } from '../../lib/motion'
import { riskBand } from '../../lib/risk'

const TOP_SOURCES = 3

interface SimilarityIndexPanelProps {
  indices: Record<string, number>
  breakdowns: Record<string, SourceContribution[]>
}

/** Turnitin-style per-document index: how much of each document matches
 * *anything* else in the scan — distinct from any single pair's score. */
export function SimilarityIndexPanel({ indices, breakdowns }: SimilarityIndexPanelProps) {
  const entries = Object.entries(indices).sort(([, a], [, b]) => b - a)
  if (entries.length === 0) return null

  return (
    <section className="card" aria-labelledby="similarity-index-title">
      <header className="card-head">
        <div>
          <h2 id="similarity-index-title" className="card-title">
            Similarity index
          </h2>
          <p className="card-subtitle">Share of each document found anywhere else in this scan.</p>
        </div>
      </header>
      <ul className="index-list">
        {entries.map(([name, index]) => {
          const sources = (breakdowns[name] ?? []).slice(0, TOP_SOURCES)
          return (
            <li key={name} className="index-row">
              <div className="index-head">
                <span className="index-name truncate" title={name}>
                  {name}
                </span>
                <span className="index-value num" data-band={riskBand(index)}>
                  {formatPercent(index)}
                </span>
              </div>
              <span className="meter meter-thin" aria-hidden="true">
                <motion.span
                  className="meter-fill"
                  data-band={riskBand(index)}
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: index }}
                  transition={spring.gentle}
                />
              </span>
              {sources.length > 0 && (
                <p className="index-sources">
                  {sources.map((s, i) => (
                    <span key={s.source}>
                      {i > 0 && <span aria-hidden="true"> · </span>}
                      <span className="truncate index-source" title={s.source}>
                        {s.source}
                      </span>{' '}
                      <span className="num">{formatPercent(s.contribution)}</span>
                    </span>
                  ))}
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
