import { motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { getPair } from '../../api/client'
import type { Algorithm, Mode, PairResponse } from '../../api/types'
import { useFocusTrap } from '../../hooks/useFocusTrap'
import type { ResultRow } from '../../lib/deriveResults'
import { ALGORITHM_LABEL, formatPercent, pluralize } from '../../lib/format'
import { EASE_OUT, spring } from '../../lib/motion'
import { IDENTICAL_SCORE } from '../../lib/risk'
import { ChevronIcon, CloseIcon, CompareIcon, DownloadIcon, RefreshIcon } from '../icons'
import { ReviewFlag, RiskPill } from '../results/RiskPill'
import { DocumentPane } from './DocumentPane'

interface ComparisonInspectorProps {
  scanId: string
  row: ResultRow
  rows: readonly ResultRow[]
  mode: Mode
  algorithm: Algorithm
  onNavigate: (row: ResultRow) => void
  onDownloadPdf: (row: ResultRow) => void
  onClose: () => void
}

type Load =
  | { state: 'loading' }
  | { state: 'ready'; data: PairResponse }
  | { state: 'error'; message: string }

const isTyping = (target: EventTarget | null) =>
  target instanceof HTMLElement && (target.isContentEditable || /INPUT|TEXTAREA|SELECT/.test(target.tagName))

export function ComparisonInspector({
  scanId,
  row,
  rows,
  mode,
  algorithm,
  onNavigate,
  onDownloadPdf,
  onClose,
}: ComparisonInspectorProps) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const dialogRef = useRef<HTMLDivElement>(null)
  useFocusTrap(dialogRef, true, onClose)

  const index = rows.findIndex((r) => r.id === row.id)
  const previous = index > 0 ? rows[index - 1] : null
  const next = index >= 0 && index < rows.length - 1 ? rows[index + 1] : null

  useEffect(() => {
    let cancelled = false
    setLoad({ state: 'loading' })
    getPair(scanId, row.fileA, row.fileB)
      .then((data) => {
        if (!cancelled) setLoad({ state: 'ready', data })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoad({ state: 'error', message: err instanceof Error ? err.message : 'Could not load this comparison.' })
        }
      })
    return () => {
      cancelled = true
    }
  }, [scanId, row.fileA, row.fileB, attempt])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return
      if (e.key === '[' && previous) onNavigate(previous)
      if (e.key === ']' && next) onNavigate(next)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [previous, next, onNavigate])

  const data = load.state === 'ready' ? load.data : null
  const identical = data ? data.file_a.text === data.file_b.text || row.score >= IDENTICAL_SCORE : false
  const noEvidence =
    data !== null && data.file_a.matched_spans.length === 0 && data.file_b.matched_spans.length === 0
  const matchedKgrams = data?.matched_kgrams ?? row.matchedKgrams

  return (
    <div className="dialog-layer">
      <motion.div
        className="overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2, ease: EASE_OUT }}
        onClick={onClose}
      />
      <motion.div
        ref={dialogRef}
        className="inspector"
        role="dialog"
        aria-modal="true"
        aria-labelledby="inspector-title"
        tabIndex={-1}
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.98, transition: { duration: 0.16 } }}
        transition={spring.drawer}
      >
        <header className="inspector-head">
          <div className="inspector-heading">
            <h2 id="inspector-title" className="inspector-title">
              <span className="truncate" title={row.fileA}>
                {row.fileA}
              </span>
              <CompareIcon size={15} />
              <span className="truncate" title={row.fileB}>
                {row.fileB}
              </span>
            </h2>
            <div className="inspector-meta">
              <span className="inspector-score num">{formatPercent(row.score)}</span>
              <RiskPill score={row.score} />
              {identical && <span className="badge badge-strong">Identical</span>}
              {row.flagged && <ReviewFlag />}
              <span className="inspector-facts">
                {ALGORITHM_LABEL[algorithm]}
                {matchedKgrams !== undefined && ` · ${pluralize(matchedKgrams, 'matched 5-gram')}`}
              </span>
            </div>
          </div>
          <div className="inspector-actions">
            <div className="button-group" role="group" aria-label="Pair navigation">
              <button
                type="button"
                className="icon-btn"
                aria-label="Previous pair"
                title="Previous pair  ["
                disabled={!previous}
                onClick={() => previous && onNavigate(previous)}
              >
                <ChevronIcon direction="left" />
              </button>
              <span className="button-group-label num" aria-hidden="true">
                {index + 1}/{rows.length}
              </span>
              <button
                type="button"
                className="icon-btn"
                aria-label="Next pair"
                title="Next pair  ]"
                disabled={!next}
                onClick={() => next && onNavigate(next)}
              >
                <ChevronIcon direction="right" />
              </button>
            </div>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onDownloadPdf(row)}>
              <DownloadIcon />
              <span className="hide-narrow">PDF</span>
            </button>
            <button type="button" className="icon-btn" aria-label="Close comparison" onClick={onClose}>
              <CloseIcon />
            </button>
          </div>
        </header>

        {data && (
          <p className="inspector-legend">
            <mark>Highlighted</mark> passages of {pluralize(data.min_match_words ?? 0, 'word')} or more appear in both
            documents.
          </p>
        )}

        {data && noEvidence && row.score > 0 && (
          <p className="notice notice-info inspector-note">
            Nothing here is long enough to highlight. The {ALGORITHM_LABEL[algorithm]} score reflects{' '}
            {mode === 'code_similarity' ? 'shared structure and identifiers' : 'shared vocabulary'} rather than
            copied passages — switch scoring back to Coverage to count only highlighted evidence.
          </p>
        )}

        <div className="inspector-body">
          {load.state === 'loading' && (
            <div className="inspector-panes" aria-busy="true">
              {[0, 1].map((i) => (
                <div key={i} className="doc-pane doc-pane-skeleton">
                  {Array.from({ length: 9 }, (_, j) => (
                    <span key={j} className="skeleton skeleton-text" style={{ width: `${90 - ((j * 13) % 45)}%` }} />
                  ))}
                </div>
              ))}
            </div>
          )}
          {load.state === 'error' && (
            <div className="inspector-error" role="alert">
              <p>{load.message}</p>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAttempt((a) => a + 1)}>
                <RefreshIcon />
                Try again
              </button>
            </div>
          )}
          {data && (
            <div className="inspector-panes">
              <DocumentPane
                label="A"
                name={data.file_a.name}
                text={data.file_a.text}
                spans={data.file_a.matched_spans}
                wrap={mode === 'text_similarity'}
              />
              <DocumentPane
                label="B"
                name={data.file_b.name}
                text={data.file_b.text}
                spans={data.file_b.matched_spans}
                wrap={mode === 'text_similarity'}
              />
            </div>
          )}
        </div>
      </motion.div>
    </div>
  )
}
