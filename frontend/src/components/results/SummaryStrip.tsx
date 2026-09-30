import { motion } from 'motion/react'
import { formatDuration, formatPercent } from '../../lib/format'
import { EASE_OUT } from '../../lib/motion'
import { riskBand } from '../../lib/risk'
import { CountUp } from './CountUp'

interface SummaryStripProps {
  maxScore: number
  flaggedCount: number
  pairCount: number
  documentCount: number
  durationSeconds?: number
}

const tile = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.3, ease: EASE_OUT } },
}

export function SummaryStrip({
  maxScore,
  flaggedCount,
  pairCount,
  documentCount,
  durationSeconds,
}: SummaryStripProps) {
  return (
    <motion.dl
      className="summary"
      initial="hidden"
      animate="shown"
      transition={{ staggerChildren: 0.05 }}
    >
      <motion.div className="summary-tile" variants={tile} data-band={riskBand(maxScore)}>
        <dt>Highest similarity</dt>
        <dd className="summary-value summary-value-risk">
          <CountUp value={maxScore} format={formatPercent} />
        </dd>
      </motion.div>
      <motion.div className="summary-tile" variants={tile}>
        <dt>Flagged for review</dt>
        <dd className="summary-value">
          <CountUp value={flaggedCount} format={(v) => String(Math.round(v))} />
          <span className="summary-of num">/ {pairCount}</span>
        </dd>
      </motion.div>
      <motion.div className="summary-tile" variants={tile}>
        <dt>Documents</dt>
        <dd className="summary-value">
          <CountUp value={documentCount} format={(v) => String(Math.round(v))} />
        </dd>
      </motion.div>
      <motion.div className="summary-tile" variants={tile}>
        <dt>Scan time</dt>
        <dd className="summary-value num">
          {durationSeconds === undefined ? '—' : formatDuration(durationSeconds)}
        </dd>
      </motion.div>
    </motion.dl>
  )
}
