import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import type { CheckResponse } from '../../api/types'
import type { ResultRow, ResultsModel } from '../../lib/deriveResults'
import { ALGORITHM_LABEL, MODE_LABEL, formatPercent } from '../../lib/format'
import { panelMotion } from '../../lib/motion'
import { ClusterIcon, GridIcon, ListIcon, RefreshIcon } from '../icons'
import { Segmented } from '../Segmented'
import { ClusterPanel } from './ClusterPanel'
import { ExportMenu } from './ExportMenu'
import type { ExportKind } from './ExportMenu'
import { HeatmapGrid } from './HeatmapGrid'
import { ResultsList } from './ResultsList'
import { ScoreHistogram } from './ScoreHistogram'
import { SimilarityIndexPanel } from './SimilarityIndexPanel'
import { SkippedFiles } from './SkippedFiles'
import { SummaryStrip } from './SummaryStrip'

type ResultsTab = 'pairs' | 'documents' | 'matrix'

interface ResultsViewProps {
  result: CheckResponse
  model: ResultsModel
  threshold: number
  source: 'scan' | 'history' | 'sample'
  settingsChanged: boolean
  selectedId: string | null
  exportBusy: ExportKind | null
  onThresholdChange: (next: number) => void
  onOpenPair: (row: ResultRow) => void
  onDownloadPdf: (row: ResultRow) => void
  onExport: (kind: ExportKind) => void
  onRerun: () => void
  onNewScan: () => void
}

export function ResultsView({
  result,
  model,
  threshold,
  source,
  settingsChanged,
  selectedId,
  exportBusy,
  onThresholdChange,
  onOpenPair,
  onDownloadPdf,
  onExport,
  onRerun,
  onNewScan,
}: ResultsViewProps) {
  const [tab, setTab] = useState<ResultsTab>('pairs')
  const ready = model.kind === 'ready' ? model : null

  const findRow = (a: string, b: string) =>
    ready?.rows.find((r) => (r.fileA === a && r.fileB === b) || (r.fileA === b && r.fileB === a))

  const title =
    source === 'history' ? 'Saved report' : source === 'sample' ? 'Benchmark demo results' : 'Analysis results'

  const hasDocIndex = Object.keys(result.similarity_indices ?? {}).length > 0

  return (
    <div className="results">
      <header className="results-head">
        <div className="results-heading">
          <h2 className="results-title">{title}</h2>
          <p className="results-meta">
            {MODE_LABEL[result.mode]} · {ALGORITHM_LABEL[result.algorithm]} scoring · min {result.min_match_words}w ·
            flagged at <span className="num">{formatPercent(threshold)}</span>
          </p>
        </div>
        <div className="results-actions">
          <ExportMenu onExport={onExport} busy={exportBusy} />
          <button type="button" className="btn btn-ghost btn-sm" onClick={onNewScan}>
            New scan
          </button>
        </div>
      </header>

      <AnimatePresence initial={false}>
        {settingsChanged && (
          <motion.div className="notice notice-info notice-row" {...panelMotion}>
            <span>Scoring or exclusion settings changed since this scan ran.</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={onRerun}>
              <RefreshIcon />
              Re-run scan
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <SkippedFiles errors={result.errors} />

      {model.kind === 'empty' ? (
        <div className="empty-result">
          <h3>{model.title}</h3>
          <p>{model.description}</p>
        </div>
      ) : (
        ready && (
          <>
            <SummaryStrip
              maxScore={ready.maxScore}
              flaggedCount={ready.flaggedCount}
              pairCount={ready.rows.length}
              documentCount={ready.names.length}
              durationSeconds={result.duration_s}
            />

            {ready.rows.length > 1 && (
              <ScoreHistogram
                bins={ready.histogram}
                threshold={threshold}
                meanScore={ready.meanScore}
                onSelectThreshold={onThresholdChange}
              />
            )}

            <div className="results-tabs-bar">
              <Segmented
                id="results-view"
                label="Results view"
                value={tab}
                onChange={setTab}
                options={[
                  {
                    value: 'pairs',
                    label: `Pairs (${ready.rows.length})`,
                    icon: <ListIcon size={15} />,
                  },
                  {
                    value: 'documents',
                    label: `Documents & clusters (${ready.names.length})`,
                    icon: <ClusterIcon size={15} />,
                  },
                  {
                    value: 'matrix',
                    label: 'Similarity matrix',
                    icon: <GridIcon size={15} />,
                  },
                ]}
              />
            </div>

            <AnimatePresence mode="wait" initial={false}>
              {tab === 'pairs' && (
                <motion.section key="pairs" className="card" aria-labelledby="pairs-title" {...panelMotion}>
                  <header className="card-head">
                    <div>
                      <h2 id="pairs-title" className="card-title">
                        {ready.layout === 'one-to-many' ? 'Compared with reference' : 'Pairwise comparison triage'}
                      </h2>
                      <p className="card-subtitle truncate">
                        {ready.layout === 'one-to-many'
                          ? ready.reference
                          : 'Click any pair to inspect synchronized side-by-side highlights and multi-algorithm scores.'}
                      </p>
                    </div>
                  </header>
                  <ResultsList
                    rows={ready.rows}
                    layout={ready.layout}
                    selectedId={selectedId}
                    onOpen={onOpenPair}
                    onDownloadPdf={onDownloadPdf}
                  />
                </motion.section>
              )}

              {tab === 'documents' && (
                <motion.div key="documents" className="results-stack" {...panelMotion}>
                  <ClusterPanel clusters={ready.clusters} threshold={threshold} onOpenPair={onOpenPair} />
                  {hasDocIndex && (
                    <SimilarityIndexPanel
                      indices={result.similarity_indices}
                      breakdowns={result.source_breakdowns}
                      files={result.files}
                      onInspectSource={(a, b) => {
                        const row = findRow(a, b)
                        if (row) onOpenPair(row)
                      }}
                    />
                  )}
                </motion.div>
              )}

              {tab === 'matrix' && (
                <motion.section key="matrix" className="card" aria-label="Similarity matrix" {...panelMotion}>
                  <header className="card-head">
                    <div>
                      <h2 className="card-title">Pairwise similarity matrix</h2>
                      <p className="card-subtitle">
                        Interactive upper-triangular heatmap · arrow keys navigate cells, Enter opens comparison.
                      </p>
                    </div>
                  </header>
                  <HeatmapGrid
                    names={ready.names}
                    scores={ready.scores}
                    threshold={threshold}
                    reference={ready.reference}
                    onSelect={(a, b) => {
                      const row = findRow(a, b)
                      if (row) onOpenPair(row)
                    }}
                  />
                </motion.section>
              )}
            </AnimatePresence>
          </>
        )
      )}
    </div>
  )
}
