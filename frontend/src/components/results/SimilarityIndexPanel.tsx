import { motion } from 'motion/react'
import type { ScanFileInfo, SourceContribution } from '../../api/types'
import { formatPercent } from '../../lib/format'
import { spring } from '../../lib/motion'
import { riskBand } from '../../lib/risk'
import { RiskPill } from './RiskPill'

const TOP_SOURCES = 4

interface SimilarityIndexPanelProps {
  indices: Record<string, number>
  breakdowns: Record<string, SourceContribution[]>
  files?: readonly ScanFileInfo[]
  onInspectSource?: (fileA: string, fileB: string) => void
}

export function SimilarityIndexPanel({
  indices,
  breakdowns,
  files,
  onInspectSource,
}: SimilarityIndexPanelProps) {
  const entries = Object.entries(indices).sort(([, a], [, b]) => b - a)
  if (entries.length === 0) return null

  const wordMap = new Map(files?.map((f) => [f.name, f.word_count]) ?? [])

  return (
    <section className="card" aria-labelledby="similarity-index-title">
      <header className="card-head">
        <h2 id="similarity-index-title" className="card-title">
          Similarity index
        </h2>
      </header>
      <ul className="index-list">
        {entries.map(([name, index]) => {
          const sources = (breakdowns[name] ?? []).slice(0, TOP_SOURCES)
          const words = wordMap.get(name)
          return (
            <li key={name} className="index-row">
              <div className="index-head">
                <div className="index-title-group">
                  <span className="index-name truncate" title={name}>
                    {name}
                  </span>
                  {words !== undefined && <span className="index-words num">{words.toLocaleString()}w</span>}
                </div>
                <div className="index-score-group">
                  <RiskPill score={index} />
                  <span className="index-value num" data-band={riskBand(index)}>
                    {formatPercent(index)}
                  </span>
                </div>
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
                <div className="index-sources">
                  {sources.map((s) =>
                    onInspectSource ? (
                      <button
                        key={s.source}
                        type="button"
                        className="index-source-btn"
                        title={`Compare ${name} with ${s.source}`}
                        onClick={() => onInspectSource(name, s.source)}
                      >
                        <span className="truncate index-source">{s.source}</span>
                        <span className="num index-source-pct">{formatPercent(s.contribution)}</span>
                      </button>
                    ) : (
                      <span key={s.source} className="index-source-static">
                        <span className="truncate index-source" title={s.source}>
                          {s.source}
                        </span>{' '}
                        <span className="num">{formatPercent(s.contribution)}</span>
                      </span>
                    ),
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
