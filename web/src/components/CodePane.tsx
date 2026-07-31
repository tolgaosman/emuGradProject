import type { ReactNode, Ref } from 'react'

export interface CodePaneSpan {
  start: number
  end: number
}

interface LineToken {
  text: string
  marked: boolean
}

interface Line {
  number: number
  tokens: LineToken[]
  touched: boolean
}

/** Split `text` into lines, marking the characters covered by `spans` and
 * flagging any line touched by at least one span (the mockup's `+` gutter
 * marker). */
function toLines(text: string, spans: CodePaneSpan[]): Line[] {
  const sorted = [...spans].sort((a, b) => a.start - b.start)
  const rawLines = text.split('\n')
  const lines: Line[] = []
  let offset = 0
  let spanIdx = 0

  for (let i = 0; i < rawLines.length; i++) {
    const raw = rawLines[i]
    const lineStart = offset
    const lineEnd = offset + raw.length
    const tokens: LineToken[] = []
    let touched = false
    let cursor = lineStart

    while (spanIdx < sorted.length && sorted[spanIdx].end <= lineStart) spanIdx += 1

    let localIdx = spanIdx
    while (localIdx < sorted.length && sorted[localIdx].start < lineEnd) {
      const span = sorted[localIdx]
      const start = Math.max(span.start, lineStart)
      const end = Math.min(span.end, lineEnd)
      if (start > cursor) tokens.push({ text: text.slice(cursor, start), marked: false })
      if (end > start) {
        tokens.push({ text: text.slice(start, end), marked: true })
        touched = true
      }
      cursor = end
      localIdx += 1
    }
    if (cursor < lineEnd) tokens.push({ text: text.slice(cursor, lineEnd), marked: false })
    if (tokens.length === 0) tokens.push({ text: '', marked: false })

    lines.push({ number: i + 1, tokens, touched })
    offset = lineEnd + 1 // +1 for the '\n' consumed by split
  }

  return lines
}

interface CodePaneProps {
  text: string
  spans: CodePaneSpan[]
  paneRef?: Ref<HTMLDivElement>
  onScroll?: () => void
}

/** Line-numbered, span-highlighted source viewer used by the inline
 * pairwise comparison card. */
export function CodePane({ text, spans, paneRef, onScroll }: CodePaneProps) {
  const lines = toLines(text, spans)

  return (
    <div className="code-pane" ref={paneRef} onScroll={onScroll}>
      <table className="code-pane-table">
        <tbody>
          {lines.map((line) => (
            <tr key={line.number} className={line.touched ? 'code-pane-row-touched' : undefined}>
              <td className="code-pane-gutter">
                <span className="code-pane-marker">{line.touched ? '+' : ''}</span>
                <span className="code-pane-line-number">{line.number}</span>
              </td>
              <td className="code-pane-code">
                <code>
                  {line.tokens.map((token, i): ReactNode =>
                    token.marked ? <mark key={i}>{token.text}</mark> : token.text,
                  )}
                </code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
