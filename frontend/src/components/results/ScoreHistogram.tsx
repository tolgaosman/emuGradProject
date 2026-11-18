import { motion } from 'motion/react'
import type { CSSProperties } from 'react'
import type { HistogramBin } from '../../lib/deriveResults'
import { formatPercent } from '../../lib/format'
import { spring } from '../../lib/motion'

interface ScoreHistogramProps {
  bins: readonly HistogramBin[]
  threshold: number
  meanScore: number
  onSelectThreshold: (next: number) => void
}

export function ScoreHistogram({ bins, threshold, meanScore, onSelectThreshold }: ScoreHistogramProps) {
  const maxCount = Math.max(1, ...bins.map((b) => b.count))
  const thresholdPct = Math.max(0, Math.min(100, threshold * 100))

  return (
    <section className="histogram-card" aria-label="Score distribution and threshold calibration">
      <div className="histogram-head">
        <div className="histogram-titles">
          <span className="histogram-title">Pair score distribution</span>
          <span className="histogram-sub num">
            Batch mean {formatPercent(meanScore)} · click a bar to calibrate threshold
          </span>
        </div>
        <span className="histogram-threshold-pill num">Threshold ≥ {formatPercent(threshold)}</span>
      </div>

      <div className="histogram-plot">
        <div
          className="histogram-marker"
          style={{ '--pos': `${thresholdPct}%` } as CSSProperties}
          aria-hidden="true"
        />
        <div className="histogram-bars" role="group" aria-label="Similarity distribution bins">
          {bins.map((bin) => {
            const ratio = bin.count / maxCount
            const isAbove = bin.max > threshold && bin.min + 0.05 >= threshold
            const targetThreshold = Math.max(0.05, Math.min(0.95, Number(bin.min.toFixed(2)) || 0.05))
            const rangeLabel = `${Math.round(bin.min * 100)}–${Math.round(bin.max * 100)}%`
            return (
              <button
                key={bin.index}
                type="button"
                className="histogram-bin"
                data-flagged={isAbove || undefined}
                data-nonempty={bin.count > 0 || undefined}
                title={`${rangeLabel}: ${bin.count} ${bin.count === 1 ? 'pair' : 'pairs'} · click to set threshold to ${formatPercent(targetThreshold)}`}
                aria-label={`${rangeLabel}, ${bin.count} pairs. Set threshold to ${formatPercent(targetThreshold)}`}
                onClick={() => onSelectThreshold(targetThreshold)}
              >
                <span className="histogram-bin-count num">{bin.count > 0 ? bin.count : ''}</span>
                <span className="histogram-bar-track">
                  <motion.span
                    className="histogram-bar-fill"
                    initial={{ scaleY: 0 }}
                    animate={{ scaleY: bin.count > 0 ? Math.max(0.12, ratio) : 0.03 }}
                    transition={spring.gentle}
                  />
                </span>
                <span className="histogram-bin-label num">{Math.round(bin.min * 100)}</span>
              </button>
            )
          })}
        </div>
      </div>
    </section>
  )
}

