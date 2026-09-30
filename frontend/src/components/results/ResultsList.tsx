import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import type { ResultRow, Workspace } from '../../lib/deriveResults'
import { formatPercent, pluralize } from '../../lib/format'
import { EASE_OUT, spring } from '../../lib/motion'
import { riskBand } from '../../lib/risk'
import { DownloadIcon } from '../icons'
import { ReviewFlag, RiskPill } from './RiskPill'

/** Rows shown before "Show all" — a class batch of 50 is 1,225 pairs. */
const INITIAL_ROWS = 12

interface ResultsListProps {
  rows: ResultRow[]
  layout: Workspace
  selectedId: string | null
  onOpen: (row: ResultRow) => void
  onDownloadPdf: (row: ResultRow) => void
}

export function ResultsList({ rows, layout, selectedId, onOpen, onDownloadPdf }: ResultsListProps) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? rows : rows.slice(0, INITIAL_ROWS)
  const hidden = rows.length - visible.length

  return (
    <div className="results-list">
      <ol className="result-rows">
        <AnimatePresence initial={false}>
          {visible.map((row, i) => {
            const title =
              layout === 'one-to-many' ? row.fileB : `${row.fileA} ↔ ${row.fileB}`
            return (
              <motion.li
                key={row.id}
                className="result-row"
                data-selected={row.id === selectedId || undefined}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.24, ease: EASE_OUT, delay: Math.min(i, INITIAL_ROWS) * 0.025 }}
              >
                <button
                  type="button"
                  className="result-main"
                  aria-label={`Compare ${title}, ${formatPercent(row.score)} similar`}
                  onClick={() => onOpen(row)}
                >
                  {row.id === selectedId && (
                    <motion.span
                      layoutId="result-selection"
                      className="result-selection"
                      transition={spring.snappy}
                      aria-hidden="true"
                    />
                  )}
                  <span className="result-rank num" aria-hidden="true">
                    {i + 1}
                  </span>
                  <span className="result-names">
                    {layout === 'one-to-many' ? (
                      <span className="result-name truncate" title={row.fileB}>
                        {row.fileB}
                      </span>
                    ) : (
                      <>
                        <span className="result-name truncate" title={row.fileA}>
                          {row.fileA}
                        </span>
                        <span className="result-name result-name-secondary truncate" title={row.fileB}>
                          {row.fileB}
                        </span>
                      </>
                    )}
                    {row.matchedKgrams !== undefined && (
                      <span className="result-meta num">
                        {pluralize(row.matchedKgrams, 'matched 5-gram')}
                      </span>
                    )}
                  </span>
                  <span className="meter" aria-hidden="true">
                    <motion.span
                      className="meter-fill"
                      data-band={riskBand(row.score)}
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: row.score }}
                      transition={{ ...spring.gentle, delay: Math.min(i, INITIAL_ROWS) * 0.025 }}
                    />
                  </span>
                  <span className="result-score num">{formatPercent(row.score)}</span>
                  <span className="result-tags">
                    <RiskPill score={row.score} />
                    {row.flagged && <ReviewFlag compact />}
                  </span>
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label={`Download PDF comparing ${row.fileA} and ${row.fileB}`}
                  title="Download highlighted PDF"
                  onClick={() => onDownloadPdf(row)}
                >
                  <DownloadIcon />
                </button>
              </motion.li>
            )
          })}
        </AnimatePresence>
      </ol>
      {rows.length > INITIAL_ROWS && (
        <button type="button" className="btn btn-ghost btn-sm results-more" onClick={() => setExpanded((e) => !e)}>
          {expanded ? 'Show top pairs only' : `Show all ${rows.length} pairs (${hidden} more)`}
        </button>
      )}
    </div>
  )
}
