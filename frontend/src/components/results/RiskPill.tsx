import { riskBand, riskLabel } from '../../lib/risk'
import { FlagIcon } from '../icons'

/** The similarity band for a score (report Table 57), coloured by severity. */
export function RiskPill({ score }: { score: number }) {
  const band = riskBand(score)
  return (
    <span className="risk-pill" data-band={band}>
      {riskLabel(band)}
    </span>
  )
}

/** "Flagged for review" marker — the report's wording (§3.3.3): the tool
 * recommends a human look, it doesn't pronounce plagiarism. */
export function ReviewFlag({ compact }: { compact?: boolean }) {
  return (
    <span className="review-flag" title="At or above your review threshold">
      <FlagIcon size={13} />
      {compact ? <span className="visually-hidden">Flagged for review</span> : 'Review'}
    </span>
  )
}
