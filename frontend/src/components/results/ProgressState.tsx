import { CheckIcon } from '../icons'

export type ProgressPhase = 'uploading' | 'processing' | 'loading'

const STEPS = ['Uploading files', 'Extracting and comparing text', 'Building the report'] as const

/** A skeleton of the results layout plus where the scan is up to. The
 * server does extraction and comparison in one request, so the middle step
 * stays active until the response lands. */
export function ProgressState({ phase }: { phase: ProgressPhase }) {
  const current = phase === 'uploading' ? 0 : 1

  return (
    <div className="progress-state" aria-busy="true">
      {phase === 'loading' ? (
        <p className="progress-title" role="status">
          Opening saved report…
        </p>
      ) : (
        <ol className="progress-steps" aria-label="Scan progress">
          {STEPS.map((label, i) => {
            const state = i < current ? 'done' : i === current ? 'active' : 'pending'
            return (
              <li key={label} className="progress-step" data-state={state} aria-current={state === 'active' ? 'step' : undefined}>
                <span className="progress-step-dot" aria-hidden="true">
                  {state === 'done' ? <CheckIcon size={12} /> : state === 'active' ? <span className="spinner spinner-xs" /> : null}
                </span>
                {label}
              </li>
            )
          })}
        </ol>
      )}

      <div className="skeleton-summary" aria-hidden="true">
        {Array.from({ length: 4 }, (_, i) => (
          <span key={i} className="skeleton skeleton-tile" />
        ))}
      </div>
      <div className="skeleton-card" aria-hidden="true">
        {Array.from({ length: 5 }, (_, i) => (
          <span key={i} className="skeleton-line-row">
            <span className="skeleton skeleton-text" style={{ width: `${62 - i * 7}%` }} />
            <span className="skeleton skeleton-bar" />
          </span>
        ))}
      </div>
    </div>
  )
}
