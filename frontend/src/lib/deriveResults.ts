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

export interface HistogramBin {
  index: number
  min: number
  max: number
  count: number
  flagged: boolean
}

export interface CopyCluster {
  id: string
  members: string[]
  pairs: ResultRow[]
  maxScore: number
  meanScore: number
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
      meanScore: number
      histogram: HistogramBin[]
      clusters: CopyCluster[]
    }

const BIN_COUNT = 10

export const pairKey = (a: string, b: string) => (a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`)

function buildHistogram(rows: readonly ResultRow[], threshold: number): HistogramBin[] {
  const counts = Array.from({ length: BIN_COUNT }, () => 0)
  for (const r of rows) {
    const idx = Math.min(BIN_COUNT - 1, Math.max(0, Math.floor(r.score * BIN_COUNT)))
    counts[idx] += 1
  }
  return counts.map((count, index) => {
    const min = index / BIN_COUNT
    const max = (index + 1) / BIN_COUNT
    return {
      index,
      min,
      max,
      count,
      flagged: max > threshold && (min >= threshold || threshold < max - 0.001),
    }
  })
}

function buildClusters(rows: readonly ResultRow[]): CopyCluster[] {
  const flaggedRows = rows.filter((r) => r.flagged)
  if (flaggedRows.length === 0) return []

  const adj = new Map<string, Set<string>>()
  for (const r of flaggedRows) {
    if (!adj.has(r.fileA)) adj.set(r.fileA, new Set())
    if (!adj.has(r.fileB)) adj.set(r.fileB, new Set())
    adj.get(r.fileA)!.add(r.fileB)
    adj.get(r.fileB)!.add(r.fileA)
  }

  const visited = new Set<string>()
  const clusters: CopyCluster[] = []

  for (const start of adj.keys()) {
    if (visited.has(start)) continue
    const members: string[] = []
    const queue = [start]
    visited.add(start)
    while (queue.length > 0) {
      const cur = queue.shift()!
      members.push(cur)
      for (const next of adj.get(cur) ?? []) {
        if (!visited.has(next)) {
          visited.add(next)
          queue.push(next)
        }
      }
    }
    const memberSet = new Set(members)
    const pairs = flaggedRows
      .filter((r) => memberSet.has(r.fileA) && memberSet.has(r.fileB))
      .sort((a, b) => b.score - a.score)
    const scores = pairs.map((p) => p.score)
    const maxScore = Math.max(...scores, 0)
    const meanScore = scores.length > 0 ? scores.reduce((s, v) => s + v, 0) / scores.length : 0
    members.sort()
    clusters.push({
      id: members.join('|'),
      members,
      pairs,
      maxScore,
      meanScore,
    })
  }

  clusters.sort((a, b) => b.maxScore - a.maxScore || b.members.length - a.members.length)
  return clusters
}

/** Turn a scan response into what the results column renders.
 *
 * Flags, histogram bins, and collusion clusters are re-derived from `threshold`
 * (the live slider value), so moving the slider updates every analytical view
 * instantaneously without re-uploading anything. */
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
  const totalScore = rows.reduce((sum, r) => sum + r.score, 0)
  return {
    kind: 'ready',
    layout,
    reference,
    names,
    scores,
    rows,
    flaggedCount: rows.filter((r) => r.flagged).length,
    maxScore: rows[0].score,
    meanScore: totalScore / rows.length,
    histogram: buildHistogram(rows, threshold),
    clusters: buildClusters(rows),
  }
}
