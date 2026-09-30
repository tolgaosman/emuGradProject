import { AnimatePresence, motion } from 'motion/react'
import { panelMotion } from '../lib/motion'
import { ArrowRightIcon } from './icons'

export type RunPhase =
  | { phase: 'ready' }
  | { phase: 'uploading'; progress: number }
  | { phase: 'processing' }

const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const RUN_SHORTCUT_LABEL = IS_MAC ? '⌘' : 'Ctrl'

interface RunBarProps {
  run: RunPhase
  /** Why the scan can't run yet; null when it can. */
  blockedReason: string | null
  onRun: () => void
  onCancel: () => void
}

export function RunBar({ run, blockedReason, onRun, onCancel }: RunBarProps) {
  return (
    <div className="run-bar">
      <AnimatePresence mode="wait" initial={false}>
        {run.phase === 'ready' ? (
          <motion.div key="ready" className="run-bar-inner" {...panelMotion}>
            <button
              type="button"
              className="btn btn-primary btn-lg btn-block"
              disabled={blockedReason !== null}
              aria-describedby={blockedReason ? 'run-blocked-reason' : undefined}
              onClick={onRun}
            >
              Run scan
              <ArrowRightIcon />
              <span className="btn-shortcut" aria-hidden="true">
                <kbd>{RUN_SHORTCUT_LABEL}</kbd>
                <kbd>↵</kbd>
              </span>
            </button>
            {blockedReason && (
              <p id="run-blocked-reason" className="run-hint">
                {blockedReason}
              </p>
            )}
          </motion.div>
        ) : (
          <motion.div key="busy" className="run-bar-inner" {...panelMotion}>
            <div className="run-status">
              <span className="spinner" aria-hidden="true" />
              <span className="run-status-label" role="status">
                {run.phase === 'uploading'
                  ? `Uploading · ${Math.round(run.progress * 100)}%`
                  : 'Comparing documents…'}
              </span>
              <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>
                Cancel
              </button>
            </div>
            <div
              className="progress"
              data-indeterminate={run.phase === 'processing' || undefined}
              role="progressbar"
              aria-label="Scan progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={run.phase === 'uploading' ? Math.round(run.progress * 100) : undefined}
            >
              <span
                className="progress-fill"
                style={run.phase === 'uploading' ? { transform: `scaleX(${run.progress})` } : undefined}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
