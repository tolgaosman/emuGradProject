import { motion } from 'motion/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { getPair } from '../../api/client'
import type { Algorithm, AlgorithmScores, Mode, PairResponse } from '../../api/types'
import { useFocusTrap } from '../../hooks/useFocusTrap'
import type { ResultRow } from '../../lib/deriveResults'
import { ALGORITHM_LABEL, formatPercent, pluralize } from '../../lib/format'
import { EASE_OUT, spring } from '../../lib/motion'
import { IDENTICAL_SCORE } from '../../lib/risk'
import { ChevronIcon, CloseIcon, CompareIcon, DownloadIcon, FoldIcon, LinkIcon, RefreshIcon } from '../icons'
import { ReviewFlag, RiskPill } from '../results/RiskPill'
import { DocumentPane } from './DocumentPane'
import type { TaggedSpan } from './DocumentPane'

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

type ResolvedCache =
  | { key: string; state: 'ready'; data: PairResponse }
  | { key: string; state: 'error'; message: string }

const isTyping = (target: EventTarget | null) =>
  target instanceof HTMLElement && (target.isContentEditable || /INPUT|TEXTAREA|SELECT/.test(target.tagName))

function buildAlgorithmItems(scores: AlgorithmScores, activeAlgo: Algorithm) {
  const entries: { key: Algorithm; label: string; value: number }[] = [
    { key: 'auto', label: 'Coverage', value: scores.coverage },
    ...(scores.ast !== null ? [{ key: 'ast' as const, label: 'AST Structure', value: scores.ast }] : []),
    { key: 'cosine', label: 'TF-IDF Cosine', value: scores.cosine },
    { key: 'winnowing', label: 'Winnowing', value: scores.winnowing },
    { key: 'jaccard', label: 'Jaccard', value: scores.jaccard },
  ]
  return entries.map((e) => ({ ...e, active: e.key === activeAlgo }))
}

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
  const [attempt, setAttempt] = useState(0)
  const [resolved, setResolved] = useState<ResolvedCache | null>(null)
  const [matchCursor, setMatchCursor] = useState<{ key: string; id: number | null; nonce: number }>({
    key: '',
    id: null,
    nonce: 0,
  })
  const [foldUnchanged, setFoldUnchanged] = useState(false)

  const dialogRef = useRef<HTMLDivElement>(null)
  useFocusTrap(dialogRef, true, onClose)

  const requestKey = `${scanId}\u0000${row.fileA}\u0000${row.fileB}\u0000${attempt}`
  const index = rows.findIndex((r) => r.id === row.id)
  const previous = index > 0 ? rows[index - 1] : null
  const next = index >= 0 && index < rows.length - 1 ? rows[index + 1] : null

  useEffect(() => {
    let cancelled = false
    getPair(scanId, row.fileA, row.fileB)
      .then((data) => {
        if (!cancelled) setResolved({ key: requestKey, state: 'ready', data })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setResolved({
            key: requestKey,
            state: 'error',
            message: err instanceof Error ? err.message : 'Could not load this comparison.',
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [scanId, row.fileA, row.fileB, attempt, requestKey])

  const current = resolved?.key === requestKey ? resolved : null
  const data = current?.state === 'ready' ? current.data : null
  const isLoading = current === null

  const { spansA, spansB, matchIds } = useMemo(() => {
    if (!data) return { spansA: [] as TaggedSpan[], spansB: [] as TaggedSpan[], matchIds: [] as number[] }
    if (data.paired_spans && data.paired_spans.length > 0) {
      return {
        spansA: data.paired_spans.map((p) => ({
          id: p.id,
          start: p.span_a[0],
          end: p.span_a[1],
          kind: p.kind,
        })),
        spansB: data.paired_spans.map((p) => ({
          id: p.id,
          start: p.span_b[0],
          end: p.span_b[1],
          kind: p.kind,
        })),
        matchIds: data.paired_spans.map((p) => p.id),
      }
    }
    const fallbackA = data.file_a.matched_spans.map(([start, end], i) => ({ id: i, start, end }))
    const fallbackB = data.file_b.matched_spans.map(([start, end], i) => ({ id: i, start, end }))
    const count = Math.max(fallbackA.length, fallbackB.length)
    return {
      spansA: fallbackA,
      spansB: fallbackB,
      matchIds: Array.from({ length: count }, (_, i) => i),
    }
  }, [data])

  const activeMatchId = matchCursor.key === requestKey ? matchCursor.id : null
  const syncNonce = matchCursor.key === requestKey ? matchCursor.nonce : 0

  const selectMatch = (id: number) => {
    setMatchCursor((prev) => ({ key: requestKey, id, nonce: prev.nonce + 1 }))
  }

  const stepMatch = (delta: number) => {
    if (matchIds.length === 0) return
    const pos = activeMatchId === null ? -1 : matchIds.indexOf(activeMatchId)
    const nextPos =
      pos === -1 ? (delta > 0 ? 0 : matchIds.length - 1) : (pos + delta + matchIds.length) % matchIds.length
    selectMatch(matchIds[nextPos])
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return
      if (e.key === '[' && previous) onNavigate(previous)
      else if (e.key === ']' && next) onNavigate(next)
      else if (e.key === 'j' && matchIds.length > 0) {
        e.preventDefault()
        stepMatch(1)
      } else if (e.key === 'k' && matchIds.length > 0) {
        e.preventDefault()
        stepMatch(-1)
      } else if (e.key === 'f') {
        e.preventDefault()
        setFoldUnchanged((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const identical = data ? data.file_a.text === data.file_b.text || row.score >= IDENTICAL_SCORE : false
  const noEvidence = data !== null && spansA.length === 0 && spansB.length === 0
  const matchedKgrams = data?.matched_kgrams ?? row.matchedKgrams
  const algoItems = data?.algorithm_scores ? buildAlgorithmItems(data.algorithm_scores, algorithm) : null
  const activePos = activeMatchId !== null ? matchIds.indexOf(activeMatchId) : -1

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
            {data && (
              <>
                <div className="button-group" role="group" aria-label="Synchronized match navigation">
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label="Previous matched block (k)"
                    title="Previous matched block  k"
                    disabled={matchIds.length === 0}
                    onClick={() => stepMatch(-1)}
                  >
                    <ChevronIcon direction="up" size={14} />
                  </button>
                  <span className="button-group-label match-sync-label num">
                    <LinkIcon size={12} />
                    {matchIds.length === 0
                      ? '0 matches'
                      : activePos >= 0
                        ? `${activePos + 1}/${matchIds.length}`
                        : pluralize(matchIds.length, 'match', 'matches')}
                  </span>
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label="Next matched block (j)"
                    title="Next matched block  j"
                    disabled={matchIds.length === 0}
                    onClick={() => stepMatch(1)}
                  >
                    <ChevronIcon direction="down" size={14} />
                  </button>
                </div>

                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  aria-pressed={foldUnchanged}
                  title="Collapse long unmatched sections  f"
                  onClick={() => setFoldUnchanged((v) => !v)}
                >
                  <FoldIcon size={14} />
                  <span className="hide-narrow">{foldUnchanged ? 'Unfold' : 'Fold unchanged'}</span>
                </button>
              </>
            )}

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

        {data && algoItems && (
          <div className="inspector-subbar">
            <div className="algo-strip" aria-label="Algorithm scores">
              {algoItems.map((item) => (
                <span key={item.key} className="algo-chip num" data-active={item.active || undefined}>
                  <span className="algo-chip-name">{item.label}</span>
                  <strong>{formatPercent(item.value)}</strong>
                </span>
              ))}
            </div>
          </div>
        )}

        {data && noEvidence && row.score > 0 && (
          <p className="notice notice-info inspector-note">
            Nothing here is long enough to highlight. The {ALGORITHM_LABEL[algorithm]} score reflects{' '}
            {mode === 'code_similarity' ? 'shared structure and identifiers' : 'shared vocabulary'} rather than
            copied passages — switch scoring back to Coverage to count only highlighted evidence.
          </p>
        )}

        <div className="inspector-body">
          {isLoading && (
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
          {current?.state === 'error' && (
            <div className="inspector-error" role="alert">
              <p>{current.message}</p>
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
                spans={spansA}
                activeMatchId={activeMatchId}
                syncNonce={syncNonce}
                foldUnchanged={foldUnchanged}
                wrap={mode === 'text_similarity'}
                onSelectMatch={selectMatch}
              />
              <DocumentPane
                label="B"
                name={data.file_b.name}
                text={data.file_b.text}
                spans={spansB}
                activeMatchId={activeMatchId}
                syncNonce={syncNonce}
                foldUnchanged={foldUnchanged}
                wrap={mode === 'text_similarity'}
                onSelectMatch={selectMatch}
              />
            </div>
          )}
        </div>
      </motion.div>
    </div>
  )
}
