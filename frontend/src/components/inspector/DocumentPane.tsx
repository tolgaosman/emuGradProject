import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { FoldIcon } from '../icons'

export interface TaggedSpan {
  id: number
  start: number
  end: number
  kind?: 'literal' | 'structural'
}

interface Token {
  text: string
  match: number | null
  isStart: boolean
}

interface Line {
  lineNo: number
  tokens: Token[]
  touched: boolean
  firstMatch: number | null
}

type RenderItem =
  | { type: 'line'; line: Line }
  | { type: 'fold'; startLine: number; endLine: number; count: number }

const CONTEXT_LINES = 2
const MIN_FOLD_RUN = 6
const EMPTY_FOLDS: ReadonlySet<number> = new Set()

/** Split `text` into lines of plain and matched runs preserving match IDs. */
function toLines(text: string, spans: readonly TaggedSpan[]): Line[] {
  const sorted = [...spans].sort((a, b) => a.start - b.start || a.end - b.end)
  const seenMatchIds = new Set<number>()
  const lines: Line[] = []
  let offset = 0
  let first = 0
  const rawLines = text.split('\n')

  for (let idx = 0; idx < rawLines.length; idx += 1) {
    const raw = rawLines[idx]
    const lineStart = offset
    const lineEnd = offset + raw.length
    const tokens: Token[] = []
    let cursor = lineStart
    let firstMatch: number | null = null

    while (first < sorted.length && sorted[first].end <= lineStart) first += 1
    for (let s = first; s < sorted.length && sorted[s].start < lineEnd; s += 1) {
      const span = sorted[s]
      const start = Math.max(span.start, lineStart)
      const end = Math.min(span.end, lineEnd)
      if (start > cursor) tokens.push({ text: text.slice(cursor, start), match: null, isStart: false })
      if (end > start) {
        const isFirstAppearance = !seenMatchIds.has(span.id)
        if (isFirstAppearance) seenMatchIds.add(span.id)
        if (firstMatch === null) firstMatch = span.id
        tokens.push({ text: text.slice(start, end), match: span.id, isStart: isFirstAppearance })
      }
      cursor = Math.max(cursor, end)
    }
    if (cursor < lineEnd) tokens.push({ text: text.slice(cursor, lineEnd), match: null, isStart: false })

    lines.push({
      lineNo: idx + 1,
      tokens,
      touched: tokens.some((t) => t.match !== null),
      firstMatch,
    })
    offset = lineEnd + 1
  }
  return lines
}

function buildRenderItems(
  lines: readonly Line[],
  foldUnchanged: boolean,
  expandedFolds: ReadonlySet<number>,
): RenderItem[] {
  if (!foldUnchanged || lines.length <= MIN_FOLD_RUN + CONTEXT_LINES * 2) {
    return lines.map((line) => ({ type: 'line', line }))
  }
  const hasAnyMatch = lines.some((l) => l.touched)
  if (!hasAnyMatch) return lines.map((line) => ({ type: 'line', line }))

  const keep = new Array<boolean>(lines.length).fill(false)
  for (let i = 0; i < lines.length; i += 1) {
    if (!lines[i].touched) continue
    const lo = Math.max(0, i - CONTEXT_LINES)
    const hi = Math.min(lines.length - 1, i + CONTEXT_LINES)
    for (let k = lo; k <= hi; k += 1) keep[k] = true
  }

  const items: RenderItem[] = []
  let i = 0
  while (i < lines.length) {
    if (keep[i]) {
      items.push({ type: 'line', line: lines[i] })
      i += 1
      continue
    }
    let j = i
    while (j < lines.length && !keep[j]) j += 1
    const count = j - i
    const startLine = lines[i].lineNo
    if (count >= MIN_FOLD_RUN && !expandedFolds.has(startLine)) {
      items.push({ type: 'fold', startLine, endLine: lines[j - 1].lineNo, count })
    } else {
      for (let k = i; k < j; k += 1) items.push({ type: 'line', line: lines[k] })
    }
    i = j
  }
  return items
}

interface DocumentPaneProps {
  label: string
  name: string
  text: string
  spans: readonly TaggedSpan[]
  activeMatchId: number | null
  syncNonce: number
  foldUnchanged: boolean
  wrap: boolean
  onSelectMatch: (id: number) => void
}

export function DocumentPane({
  label,
  name,
  text,
  spans,
  activeMatchId,
  syncNonce,
  foldUnchanged,
  wrap,
  onSelectMatch,
}: DocumentPaneProps) {
  const lines = useMemo(() => toLines(text, spans), [text, spans])
  const [expandedKey, setExpandedKey] = useState<{ text: string; folds: Set<number> }>({
    text,
    folds: new Set(),
  })
  const expandedFolds = expandedKey.text === text ? expandedKey.folds : EMPTY_FOLDS
  const bodyRef = useRef<HTMLDivElement>(null)

  const renderItems = useMemo(
    () => buildRenderItems(lines, foldUnchanged, expandedFolds),
    [lines, foldUnchanged, expandedFolds],
  )

  const minimapMarkers = useMemo(() => {
    const total = Math.max(1, lines.length)
    const byId = new Map<number, number>()
    for (let i = 0; i < lines.length; i += 1) {
      const m = lines[i].firstMatch
      if (m !== null && !byId.has(m)) byId.set(m, i / total)
    }
    return Array.from(byId.entries()).map(([id, ratio]) => ({ id, ratio }))
  }, [lines])

  useEffect(() => {
    if (activeMatchId === null) return
    const body = bodyRef.current
    const target = body?.querySelector<HTMLElement>(`[data-match="${activeMatchId}"]`)
    if (!body || !target) return
    const offset = target.getBoundingClientRect().top - body.getBoundingClientRect().top + body.scrollTop
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    body.scrollTo({ top: Math.max(0, offset - body.clientHeight / 3), behavior: reduce ? 'auto' : 'smooth' })
  }, [activeMatchId, syncNonce, foldUnchanged])

  const expandFold = (startLine: number) => {
    setExpandedKey((prev) => {
      const base = prev.text === text ? prev.folds : new Set<number>()
      const next = new Set(base)
      next.add(startLine)
      return { text, folds: next }
    })
  }

  return (
    <section className="doc-pane" aria-label={`${label}: ${name}`}>
      <header className="doc-pane-head">
        <div className="doc-pane-heading">
          <span className="doc-pane-label">{label}</span>
          <span className="doc-pane-name truncate" title={name}>
            {name}
          </span>
        </div>
        <span className="doc-pane-stats num">
          {lines.length.toLocaleString()} {lines.length === 1 ? 'line' : 'lines'}
        </span>
      </header>

      <div className="doc-pane-viewport">
        <div ref={bodyRef} className="doc-pane-body" data-wrap={wrap || undefined} tabIndex={0}>
          {renderItems.map((item) =>
            item.type === 'fold' ? (
              <button
                key={`fold-${item.startLine}`}
                type="button"
                className="doc-fold-row num"
                onClick={() => expandFold(item.startLine)}
              >
                <FoldIcon size={12} />
                <span>
                  {item.count} unchanged lines ({item.startLine}–{item.endLine}) — click to expand
                </span>
              </button>
            ) : (
              <div
                key={item.line.lineNo}
                className="doc-line"
                data-touched={item.line.touched || undefined}
                data-active-line={
                  (activeMatchId !== null && item.line.tokens.some((t) => t.match === activeMatchId)) || undefined
                }
              >
                <span className="doc-line-no num" aria-hidden="true">
                  {item.line.lineNo}
                </span>
                <code className="doc-line-code">
                  {item.line.tokens.map((token, j) =>
                    token.match === null ? (
                      token.text
                    ) : (
                      <mark
                        key={j}
                        data-match={token.match}
                        data-active={token.match === activeMatchId || undefined}
                        title={`Match #${token.match + 1} — click to sync both panes`}
                        onClick={() => onSelectMatch(token.match!)}
                      >
                        {token.isStart && (
                          <span className="match-tag num" aria-hidden="true">
                            #{token.match + 1}
                          </span>
                        )}
                        {token.text}
                      </mark>
                    ),
                  )}
                  {item.line.tokens.length === 0 && '\u00A0'}
                </code>
              </div>
            ),
          )}
        </div>

        {minimapMarkers.length > 0 && (
          <div className="doc-minimap" aria-label={`Match minimap for ${name}`}>
            {minimapMarkers.map((m) => (
              <button
                key={m.id}
                type="button"
                className="doc-minimap-tick"
                data-active={m.id === activeMatchId || undefined}
                style={{ '--top': `${Math.min(97, Math.max(1, m.ratio * 100))}%` } as CSSProperties}
                title={`Jump to match #${m.id + 1}`}
                aria-label={`Jump to match ${m.id + 1}`}
                onClick={() => onSelectMatch(m.id)}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
