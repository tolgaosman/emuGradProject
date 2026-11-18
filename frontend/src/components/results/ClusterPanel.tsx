import type { CopyCluster, ResultRow } from '../../lib/deriveResults'
import { formatPercent } from '../../lib/format'
import { ClusterIcon, CompareIcon } from '../icons'
import { RiskPill } from './RiskPill'

interface ClusterPanelProps {
  clusters: readonly CopyCluster[]
  onOpenPair: (row: ResultRow) => void
}

export function ClusterPanel({ clusters, onOpenPair }: ClusterPanelProps) {
  if (clusters.length === 0) return null

  return (
    <section className="card" aria-labelledby="clusters-title">
      <header className="card-head">
        <h2 id="clusters-title" className="card-title">
          Clusters ({clusters.length})
        </h2>
      </header>
      <div className="cluster-list">
        {clusters.map((cluster, idx) => {
          const topPair = cluster.pairs[0]
          return (
            <article key={cluster.id} className="cluster-card">
              <div className="cluster-card-head">
                <div className="cluster-heading">
                  <span className="cluster-badge num">
                    <ClusterIcon size={13} />#{idx + 1}
                  </span>
                  <span className="cluster-stats num">
                    {cluster.members.length} files · mean {formatPercent(cluster.meanScore)}
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
                      Inspect
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
            </article>
          )
        })}
      </div>
    </section>
  )
}
