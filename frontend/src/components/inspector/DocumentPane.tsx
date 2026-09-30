import { useEffect, useMemo, useRef, useState } from 'react'
import { pluralize } from '../../lib/format'
import { ChevronIcon } from '../icons'

interface Token {
  text: string
  /** Index of the matched span this text belongs to, in reading order. */
  match: number | null
}

interface Line {
  tokens: Token[]
  touched: boolean
}

/** Split `text` into lines of plain and matched runs. A span that crosses
 * lines yields one run per line, all tagged with the same match index. */
function toLines(text: string, spans: readonly [number, number][]): Line[] {
  const sorted = [...spans].sort((a, b) => a[0] - b[0])
  const lines: Line[] = []
  let offset = 0
  let first = 0

  for (const raw of text.split('\n')) {
    const lineStart = offset
    const lineEnd = offset + raw.length
    const tokens: Token[] = []
    let cursor = lineStart

    while (first < sorted.length && sorted[first][1] <= lineStart) first += 1
    for (let s = first; s < sorted.length && sorted[s][0] < lineEnd; s += 1) {
      const start = Math.max(sorted[s][0], lineStart)
      const end = Math.min(sorted[s][1], lineEnd)
      if (start > cursor) tokens.push({ text: text.slice(cursor, start), match: null })
      if (end > start) tokens.push({ text: text.slice(start, end), match: s })
      cursor = Math.max(cursor, end)
    }
    if (cursor < lineEnd) tokens.push({ text: text.slice(cursor, lineEnd), match: null })

    lines.push({ tokens, touched: tokens.some((t) => t.match !== null) })
    offset = lineEnd + 1
  }
  return lines
}

interface DocumentPaneProps {
  label: string
  name: string
  text: string
  spans: readonly [number, number][]
  /** Prose wraps; source code keeps its lines. */
  wrap: boolean
}

export function DocumentPane({ label, name, text, spans, wrap }: DocumentPaneProps) {
  const lines = useMemo(() => toLines(text, spans), [text, spans])
  const [active, setActive] = useState<number | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const count = spans.length

  useEffect(() => {
    if (active === null) return
    const body = bodyRef.current
    const target = body?.querySelector<HTMLElement>(`[data-match="${active}"]`)
    if (!body || !target) return
    const offset =
      target.getBoundingClientRect().top - body.getBoundingClientRect().top + body.scrollTop
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    body.scrollTo({ top: offset - body.clientHeight / 3, behavior: reduce ? 'auto' : 'smooth' })
  }, [active])

  const step = (delta: number) => {
    if (count === 0) return
    setActive((current) => (current === null ? (delta > 0 ? 0 : count - 1) : (current + delta + count) % count))
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
        <div className="match-nav">
          <span className="match-nav-count num" aria-live="polite">
            {count === 0
              ? 'No matches'
              : active === null
                ? pluralize(count, 'match', 'matches')
                : `${active + 1} of ${count}`}
          </span>
          <button
            type="button"
            className="icon-btn icon-btn-sm"
            aria-label={`Previous match in ${name}`}
            disabled={count === 0}
            onClick={() => step(-1)}
          >
            <ChevronIcon direction="up" size={14} />
          </button>
          <button
            type="button"
            className="icon-btn icon-btn-sm"
            aria-label={`Next match in ${name}`}
            disabled={count === 0}
            onClick={() => step(1)}
          >
            <ChevronIcon direction="down" size={14} />
          </button>
        </div>
      </header>
      <div ref={bodyRef} className="doc-pane-body" data-wrap={wrap || undefined} tabIndex={0}>
        {lines.map((line, i) => (
          <div key={i} className="doc-line" data-touched={line.touched || undefined}>
            <span className="doc-line-no num" aria-hidden="true">
              {i + 1}
            </span>
            <code className="doc-line-code">
              {line.tokens.map((token, j) =>
                token.match === null ? (
                  token.text
                ) : (
                  <mark key={j} data-match={token.match} data-active={token.match === active || undefined}>
                    {token.text}
                  </mark>
                ),
              )}
              {line.tokens.length === 0 && ' '}
            </code>
          </div>
        ))}
      </div>
    </section>
  )
}
