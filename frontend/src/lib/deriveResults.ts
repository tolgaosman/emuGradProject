import type { CheckResponse } from '../api/types'
import { isFlagged } from './risk'

/** How a scan's results are laid out: one reference checked against the
 * rest, or every document against every other (a class batch). */
export type Workspace = 'one-to-many' | 'batch'

export interface ResultRow {
  id: string
  fileA: string
  fileB: string
  score: number
  flagged: boolean
  matchedKgrams?: number
}

export type ResultsModel =
  | { kind: 'empty'; title: string; description: string }
  | {
      kind: 'ready'
      layout: Workspace
      /** Set for the one-to-many layout. */
      reference?: string
      names: string[]
      scores: number[][]
      /** Ranked highest score first. */
      rows: ResultRow[]
      flaggedCount: number
      maxScore: number
    }

const pairKey = (a: string, b: string) => (a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`)

/** Turn a scan response into what the results column renders.
 *
 * Flags are re-derived from `threshold` (the live slider value), since a flag
 * is only `score >= threshold` — moving the slider after a scan updates the
 * view instantly without re-uploading anything. */
export function deriveResults(
  result: CheckResponse,
  layout: Workspace,
  threshold: number,
  referenceName?: string,
): ResultsModel {
  const names = result.matrix?.names ?? []
  const scores = result.matrix?.scores ?? []

  if (names.length === 0) {
    return {
      kind: 'empty',
      title: 'No comparable files',
      description: 'Every uploaded file was skipped. The reasons are listed above.',
    }
  }

  const kgrams = new Map(result.pairs.map((p) => [pairKey(p.file_a, p.file_b), p.matched_kgrams]))
  const row = (i: number, j: number): ResultRow => {
    const score = scores[i]?.[j] ?? 0
    return {
      id: pairKey(names[i], names[j]),
      fileA: names[i],
      fileB: names[j],
      score,
      flagged: isFlagged(score, threshold),
      matchedKgrams: kgrams.get(pairKey(names[i], names[j])),
    }
  }

  let rows: ResultRow[] = []
  let reference: string | undefined

  if (layout === 'one-to-many') {
    // The reference is always uploaded first; find it by position so a name
    // the server sanitized still resolves. Older servers lack `files`.
    reference =
      result.files?.find((f) => f.index === 0)?.name ??
      (referenceName && names.includes(referenceName) ? referenceName : undefined)
    if (reference === undefined) {
      const refError = result.errors.find((e) => e.file === referenceName) ?? result.errors[0]
      return {
        kind: 'empty',
        title: 'The reference file couldn’t be read',
        description: refError
          ? `${refError.file}: ${refError.error}`
          : 'There is nothing to compare the other files against.',
      }
    }
    const refIdx = names.indexOf(reference)
    rows = names.flatMap((_, j) => (j === refIdx ? [] : [row(refIdx, j)]))
  } else {
    for (let i = 0; i < names.length; i += 1) {
      for (let j = i + 1; j < names.length; j += 1) rows.push(row(i, j))
    }
  }

  if (rows.length === 0) {
    return {
      kind: 'empty',
      title: 'Only one document to look at',
      description:
        'A similarity check needs at least two readable documents. Add another file and run the scan again.',
    }
  }

  rows.sort((a, b) => b.score - a.score)
  return {
    kind: 'ready',
    layout,
    reference,
    names,
    scores,
    rows,
    flaggedCount: rows.filter((r) => r.flagged).length,
    maxScore: rows[0].score,
  }
}
