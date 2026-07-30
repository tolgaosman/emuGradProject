import { useEffect, useRef, useState } from 'react'
import { getPair } from '../api/client'
import type { PairResponse } from '../api/types'
import { CodePane } from './CodePane'
import { SkeletonLoader } from './SkeletonLoader'

interface ComparisonInspectorProps {
  scanId: string
  fileA: string
  fileB: string
  score: number
  onClose: () => void
}

/** Inline side-by-side comparison card, rendered in the results column
 * below the similarity matrix (not a modal) — matches the mockup's
 * `84% Match` panel. */
export function ComparisonInspector({ scanId, fileA, fileB, score, onClose }: ComparisonInspectorProps) {
  const [data, setData] = useState<PairResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const paneA = useRef<HTMLDivElement>(null)
  const paneB = useRef<HTMLDivElement>(null)
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
    <div className="card inspector-card">
      <div className="card-head inspector-head">
        <h3>
          {fileA} <span className="inspector-vs">↔</span> {fileB}
        </h3>
        <div className="inspector-head-right">
          <span className={`badge ${score >= 0.9 ? 'badge-high' : 'badge-mid'}`}>
            {Math.round(score * 100)}% Match
          </span>
          <button type="button" className="inspector-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>
      </div>

      {error && <div className="inspector-error">{error}</div>}
      {!data && !error && <SkeletonLoader label="Loading comparison…" />}

      {data && (
        <div className="inspector-panes">
          <CodePane
            text={data.file_a.text}
            spans={data.file_a.matched_spans.map(([start, end]) => ({ start, end }))}
            paneRef={paneA}
            onScroll={() => syncScroll('a')}
          />
          <CodePane
            text={data.file_b.text}
            spans={data.file_b.matched_spans.map(([start, end]) => ({ start, end }))}
            paneRef={paneB}
            onScroll={() => syncScroll('b')}
          />
        </div>
      )}
    </div>
  )
}
