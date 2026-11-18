import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import type { CheckResponse } from '../../api/types'
import type { ResultRow, ResultsModel } from '../../lib/deriveResults'
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

  const hasDocIndex = Object.keys(result.similarity_indices ?? {}).length > 0

  return (
    <div className="results">
      <header className="results-topbar">
        {ready ? (
          <Segmented
            id="results-view"
            label="Results view"
            size="sm"
            value={tab}
            onChange={setTab}
            options={[
              {
                value: 'pairs',
                label: `Pairs · ${ready.rows.length}`,
                icon: <ListIcon size={14} />,
              },
              {
                value: 'documents',
                label: `Files · ${ready.names.length}`,
                icon: <ClusterIcon size={14} />,
              },
              {
                value: 'matrix',
                label: 'Matrix',
                icon: <GridIcon size={14} />,
              },
            ]}
          />
        ) : (
          <span />
        )}

        <div className="results-actions">
          {settingsChanged && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onRerun}>
              <RefreshIcon size={14} />
              Re-run
            </button>
          )}
          <ExportMenu onExport={onExport} busy={exportBusy} />
          <button type="button" className="btn btn-ghost btn-sm" onClick={onNewScan}>
            Clear scan
          </button>
        </div>
      </header>

      <SkippedFiles errors={result.errors} />

      {model.kind === 'empty' ? (
        <div className="empty-result">
          <h3>{model.title}</h3>
          <p>{model.description}</p>
        </div>
      ) : (
        ready && (
          <>
            <div className="results-overview">
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
            </div>

            <AnimatePresence mode="wait" initial={false}>
              {tab === 'pairs' && (
                <motion.section key="pairs" className="card" aria-label="Pairs" {...panelMotion}>
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
                  <ClusterPanel clusters={ready.clusters} onOpenPair={onOpenPair} />
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
