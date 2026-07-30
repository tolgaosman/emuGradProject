import { useEffect, useRef, useState } from 'react'
import { getPair } from '../api/client'
import type { PairResponse } from '../api/types'
import { SkeletonLoader } from './SkeletonLoader'

interface ComparisonInspectorProps {
  scanId: string
  fileA: string
  fileB: string
  score: number
  onClose: () => void
}

function renderHighlighted(text: string, spans: [number, number][]) {
  if (spans.length === 0) return text
  const nodes: React.ReactNode[] = []
  let cursor = 0
  spans.forEach(([start, end], i) => {
    if (start > cursor) nodes.push(text.slice(cursor, start))
    nodes.push(<mark key={i}>{text.slice(start, end)}</mark>)
    cursor = end
  })
  if (cursor < text.length) nodes.push(text.slice(cursor))
  return nodes
}

export function ComparisonInspector({ scanId, fileA, fileB, score, onClose }: ComparisonInspectorProps) {
  const [data, setData] = useState<PairResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const paneA = useRef<HTMLPreElement>(null)
  const paneB = useRef<HTMLPreElement>(null)
  const syncing = useRef(false)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(null)
    getPair(scanId, fileA, fileB)
      .then((res) => {
        if (!cancelled) setData(res)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load comparison.')
      })
    return () => {
      cancelled = true
    }
  }, [scanId, fileA, fileB])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const syncScroll = (source: 'a' | 'b') => {
    if (syncing.current) return
    const from = source === 'a' ? paneA.current : paneB.current
    const to = source === 'a' ? paneB.current : paneA.current
    if (!from || !to) return
    syncing.current = true
    const ratio = from.scrollTop / Math.max(1, from.scrollHeight - from.clientHeight)
    to.scrollTop = ratio * Math.max(1, to.scrollHeight - to.clientHeight)
    syncing.current = false
  }

  return (
    <div className="inspector-overlay" onClick={onClose}>
      <div className="inspector-panel" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <header className="inspector-header">
          <div>
            <h3>
              {fileA} <span className="inspector-vs">↔</span> {fileB}
            </h3>
            <span className={`badge ${score >= 0.9 ? 'badge-high' : 'badge-mid'}`}>
              {score.toFixed(4)}
            </span>
          </div>
          <button type="button" className="inspector-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>

        {error && <div className="inspector-error">{error}</div>}
        {!data && !error && <SkeletonLoader label="Loading comparison…" />}

        {data && (
          <div className="inspector-panes">
            <pre
              className="inspector-pane"
              ref={paneA}
              onScroll={() => syncScroll('a')}
            >
              <code>{renderHighlighted(data.file_a.text, data.file_a.matched_spans)}</code>
            </pre>
            <pre
              className="inspector-pane"
              ref={paneB}
              onScroll={() => syncScroll('b')}
            >
              <code>{renderHighlighted(data.file_b.text, data.file_b.matched_spans)}</code>
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
