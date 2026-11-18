import type { CopyCluster, ResultRow } from '../../lib/deriveResults'
import { formatPercent, pluralize } from '../../lib/format'
import { ClusterIcon, CompareIcon } from '../icons'
import { RiskPill } from './RiskPill'

interface ClusterPanelProps {
  clusters: readonly CopyCluster[]
  threshold: number
  onOpenPair: (row: ResultRow) => void
}

export function ClusterPanel({ clusters, threshold, onOpenPair }: ClusterPanelProps) {
  if (clusters.length === 0) {
    return (
      <section className="card" aria-label="Collusion clusters">
        <header className="card-head">
          <div>
            <h2 className="card-title">Copy clusters</h2>
            <p className="card-subtitle">
              No connected document groups meet the {formatPercent(threshold)} review threshold.
            </p>
          </div>
        </header>
      </section>
    )
  }

  return (
    <section className="card" aria-labelledby="clusters-title">
      <header className="card-head">
        <div>
          <h2 id="clusters-title" className="card-title">
            Flagged copy clusters ({clusters.length})
          </h2>
          <p className="card-subtitle">
            Connected groups of submissions linked by pairs at or above {formatPercent(threshold)}.
          </p>
        </div>
      </header>
      <div className="cluster-list">
        {clusters.map((cluster, idx) => {
          const topPair = cluster.pairs[0]
          return (
            <article key={cluster.id} className="cluster-card">
              <div className="cluster-card-head">
                <div className="cluster-heading">
                  <span className="cluster-badge num">
                    <ClusterIcon size={13} />
                    Group {idx + 1}
                  </span>
                  <span className="cluster-stats num">
                    {pluralize(cluster.members.length, 'document')} · {pluralize(cluster.pairs.length, 'flagged link')} · mean{' '}
                    {formatPercent(cluster.meanScore)}
                  </span>
                </div>
                <div className="cluster-actions">
                  <RiskPill score={cluster.maxScore} />
                  {topPair && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      onClick={() => onOpenPair(topPair)}
                    >
                      <CompareIcon size={13} />
                      Inspect top ({formatPercent(topPair.score)})
                    </button>
                  )}
                </div>
              </div>

              <div className="cluster-members" aria-label="Documents in group">
                {cluster.members.map((member) => (
                  <span key={member} className="cluster-member truncate" title={member}>
                    {member}
                  </span>
                ))}
              </div>

              {cluster.pairs.length > 1 && (
                <div className="cluster-links">
                  {cluster.pairs.slice(0, 4).map((pair) => (
                    <button
                      key={pair.id}
                      type="button"
                      className="cluster-link-chip"
                      onClick={() => onOpenPair(pair)}
                    >
                      <span className="truncate">{pair.fileA}</span>
                      <span aria-hidden="true">↔</span>
                      <span className="truncate">{pair.fileB}</span>
                      <strong className="num">{formatPercent(pair.score)}</strong>
                    </button>
                  ))}
                </div>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}

