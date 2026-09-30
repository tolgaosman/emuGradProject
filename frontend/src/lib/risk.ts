/** Similarity bands from the project report (Table 57). They describe how
 * much of a document is matched; whether a pair is *flagged for review* is
 * a separate question, answered by the user's threshold. */
export type RiskBand = 'veryhigh' | 'high' | 'moderate' | 'low'

const BANDS: readonly { band: RiskBand; min: number; label: string }[] = [
  { band: 'veryhigh', min: 0.9, label: 'Very high' },
  { band: 'high', min: 0.7, label: 'High' },
  { band: 'moderate', min: 0.5, label: 'Moderate' },
  { band: 'low', min: 0, label: 'Low' },
]

/** Scores at or above this are treated as the same document (proposal item 1:
 * "checking if two documents are identical"). Coverage rarely reaches an exact
 * 1.0 because text before the first token and after the last is unmatched. */
export const IDENTICAL_SCORE = 0.995

export function riskBand(score: number): RiskBand {
  return (BANDS.find((b) => score >= b.min) ?? BANDS[BANDS.length - 1]).band
}

export function riskLabel(band: RiskBand): string {
  return BANDS.find((b) => b.band === band)?.label ?? ''
}

export const isFlagged = (score: number, threshold: number) => score >= threshold
