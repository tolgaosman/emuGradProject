import { AnimatePresence, motion } from 'motion/react'
import { useMemo, useState } from 'react'
import type { ResultRow, Workspace } from '../../lib/deriveResults'
import { formatPercent, pluralize } from '../../lib/format'
import { EASE_OUT, spring } from '../../lib/motion'
import { riskBand } from '../../lib/risk'
import { CloseIcon, DownloadIcon, SearchIcon } from '../icons'
import { ReviewFlag, RiskPill } from './RiskPill'

/** Rows shown before "Show all" — a class batch of 50 is 1,225 pairs. */
const INITIAL_ROWS = 15

type FilterMode = 'all' | 'flagged' | 'high' | 'moderate'
type SortMode = 'score' | 'kgrams' | 'name'

interface ResultsListProps {
  rows: ResultRow[]
  layout: Workspace
  selectedId: string | null
  onOpen: (row: ResultRow) => void
  onDownloadPdf: (row: ResultRow) => void
}

export function ResultsList({ rows, layout, selectedId, onOpen, onDownloadPdf }: ResultsListProps) {
  const [expanded, setExpanded] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FilterMode>('all')
  const [sortBy, setSortBy] = useState<SortMode>('score')

  const flaggedCount = useMemo(() => rows.filter((r) => r.flagged).length, [rows])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = rows.filter((row) => {
      if (q && !row.fileA.toLowerCase().includes(q) && !row.fileB.toLowerCase().includes(q)) {
        return false
      }
      if (filter === 'flagged') return row.flagged
      if (filter === 'high') return row.score >= 0.7
      if (filter === 'moderate') return row.score >= 0.5 && row.score < 0.7
      return true
    })

    if (sortBy === 'kgrams') {
      list.sort((a, b) => (b.matchedKgrams ?? 0) - (a.matchedKgrams ?? 0) || b.score - a.score)
    } else if (sortBy === 'name') {
      list.sort((a, b) => a.fileA.localeCompare(b.fileA) || a.fileB.localeCompare(b.fileB))
    } else {
      list.sort((a, b) => b.score - a.score)
    }
    return list
  }, [rows, query, filter, sortBy])

  const visible = expanded ? filtered : filtered.slice(0, INITIAL_ROWS)
  const hidden = filtered.length - visible.length

  return (
    <div className="results-list">
      {rows.length > 1 && (
        <div className="triage-bar">
          <div className="search-field">
            <SearchIcon size={14} />
            <input
              type="search"
              className="search-input"
              placeholder="Filter by file name…"
              aria-label="Filter pairs by file name"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {query && (
              <button
                type="button"
                className="icon-btn icon-btn-sm search-clear"
                aria-label="Clear search"
                onClick={() => setQuery('')}
              >
                <CloseIcon size={12} />
              </button>
            )}
          </div>

          <div className="triage-filters" role="group" aria-label="Filter pairs">
            {(
              [
                { id: 'all', label: `All (${rows.length})` },
                { id: 'flagged', label: `Flagged (${flaggedCount})` },
                { id: 'high', label: '≥ 70%' },
                { id: 'moderate', label: '50–69%' },
              ] as const
            ).map((opt) => (
              <button
                key={opt.id}
                type="button"
                className="filter-pill num"
                aria-pressed={filter === opt.id}
                onClick={() => setFilter(opt.id)}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <select
            className="select select-sm triage-sort"
            aria-label="Sort pairs by"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortMode)}
          >
            <option value="score">Sort: Highest similarity</option>
            <option value="kgrams">Sort: Matched 5-grams</option>
            <option value="name">Sort: File name</option>
          </select>
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="triage-empty">
          <p>No document pairs match the active filter.</p>
          <button
            type="button"
            className="btn btn-secondary btn-xs"
            onClick={() => {
              setQuery('')
              setFilter('all')
            }}
          >
            Reset filters
          </button>
        </div>
      ) : (
        <ol className="result-rows">
          <AnimatePresence initial={false}>
            {visible.map((row, i) => {
              const title = layout === 'one-to-many' ? row.fileB : `${row.fileA} ↔ ${row.fileB}`
              return (
                <motion.li
                  key={row.id}
                  className="result-row"
                  data-selected={row.id === selectedId || undefined}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2, ease: EASE_OUT, delay: Math.min(i, 10) * 0.02 }}
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
                        transition={{ ...spring.gentle, delay: Math.min(i, 10) * 0.02 }}
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
      )}

      {filtered.length > INITIAL_ROWS && (
        <button type="button" className="btn btn-ghost btn-sm results-more" onClick={() => setExpanded((e) => !e)}>
          {expanded ? 'Show top pairs only' : `Show all ${filtered.length} pairs (${hidden} more)`}
        </button>
      )}
    </div>
  )
}
