import type { Algorithm, Language, Mode } from '../api/types'

export const MODE_LABEL: Record<Mode, string> = {
  text_similarity: 'Text',
  code_similarity: 'Code',
}

export const ALGORITHM_LABEL: Record<Algorithm, string> = {
  auto: 'Coverage',
  cosine: 'Cosine',
  winnowing: 'Winnowing',
  jaccard: 'Jaccard',
  ast: 'AST',
}

/** One-line explanations, condensed from the report's §5.2. */
export const ALGORITHM_HINT: Record<Algorithm, string> = {
  auto: 'Share of each document covered by matching passages — exactly what gets highlighted.',
  cosine: 'TF-IDF vectors compared by angle: overall vocabulary overlap.',
  winnowing: 'Rolling-hash fingerprints of 5-word phrases; robust to small edits.',
  jaccard: 'Overlap of the two documents’ stemmed word sets.',
  ast: 'Python syntax trees with identifiers normalized; catches renamed copies.',
}

export const LANGUAGE_LABEL: Record<Language, string> = {
  text: 'Text',
  python: 'Python',
  java: 'Java',
  c: 'C',
  cpp: 'C++',
}

export const formatPercent = (score: number) => `${Math.round(score * 100)}%`

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatDuration(seconds: number): string {
  return seconds < 10 ? `${seconds.toFixed(2)} s` : `${Math.round(seconds)} s`
}

const relativeFormatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
const RELATIVE_STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
  ['week', 4.35],
  ['month', 12],
  ['year', Infinity],
]

export function formatRelativeTime(iso: string, now = Date.now()): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return ''
  let value = (then - now) / 1000
  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(value) < size) return relativeFormatter.format(Math.round(value), unit)
    value /= size
  }
  return ''
}

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot === -1 ? '' : name.slice(dot).toLowerCase()
}

export function stem(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot > 0 ? name.slice(0, dot) : name
}

export const pluralize = (count: number, singular: string, plural = `${singular}s`) =>
  `${count} ${count === 1 ? singular : plural}`
