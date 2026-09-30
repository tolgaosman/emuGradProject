import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import type { CheckResponse } from '../../api/types'
import type { ResultRow, ResultsModel } from '../../lib/deriveResults'
import { ALGORITHM_LABEL, MODE_LABEL, formatPercent } from '../../lib/format'
import { panelMotion } from '../../lib/motion'
import { GridIcon, ListIcon, RefreshIcon } from '../icons'
import { Segmented } from '../Segmented'
import { ExportMenu } from './ExportMenu'
import type { ExportKind } from './ExportMenu'
import { HeatmapGrid } from './HeatmapGrid'
import { ResultsList } from './ResultsList'
import { SimilarityIndexPanel } from './SimilarityIndexPanel'
import { SkippedFiles } from './SkippedFiles'
import { SummaryStrip } from './SummaryStrip'

type View = 'list' | 'matrix'

const VIEW_OPTIONS = [
  { value: 'list', label: 'Ranked list', icon: <ListIcon /> },
  { value: 'matrix', label: 'Matrix', icon: <GridIcon /> },
] as const

interface ResultsViewProps {
  result: CheckResponse
  model: ResultsModel
  threshold: number
  fromHistory: boolean
  settingsChanged: boolean
  selectedId: string | null
  exportBusy: ExportKind | null
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
  fromHistory,
  settingsChanged,
  selectedId,
  exportBusy,
  onOpenPair,
  onDownloadPdf,
  onExport,
  onRerun,
  onNewScan,
}: ResultsViewProps) {
  const [view, setView] = useState<View>('list')
  const ready = model.kind === 'ready' ? model : null

  const findRow = (a: string, b: string) =>
    ready?.rows.find((r) => (r.fileA === a && r.fileB === b) || (r.fileA === b && r.fileB === a))

  return (
    <div className="results">
      <header className="results-head">
        <div className="results-heading">
          <h2 className="results-title">{fromHistory ? 'Saved report' : 'Results'}</h2>
          <p className="results-meta">
            {MODE_LABEL[result.mode]} · {ALGORITHM_LABEL[result.algorithm]} scoring · flagged at{' '}
            <span className="num">{formatPercent(threshold)}</span>
          </p>
        </div>
        <div className="results-actions">
          {ready && (
            <Segmented id="results-view" size="sm" iconOnly label="Results view" options={VIEW_OPTIONS} value={view} onChange={setView} />
          )}
          <ExportMenu onExport={onExport} busy={exportBusy} />
          <button type="button" className="btn btn-ghost btn-sm" onClick={onNewScan}>
            New scan
          </button>
        </div>
      </header>

      <AnimatePresence initial={false}>
        {settingsChanged && (
          <motion.div className="notice notice-info notice-row" {...panelMotion}>
            <span>Scoring settings changed since this scan ran.</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={onRerun}>
              <RefreshIcon />
              Re-run
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

          <section className="card" aria-labelledby="pairs-title">
            <header className="card-head">
              <div>
                <h2 id="pairs-title" className="card-title">
                  {ready.layout === 'one-to-many' ? 'Compared with the reference' : 'Most similar pairs'}
                </h2>
                <p className="card-subtitle truncate">
                  {ready.layout === 'one-to-many'
                    ? ready.reference
                    : 'Every document against every other, highest first.'}
                </p>
              </div>
            </header>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={view} {...panelMotion}>
                {view === 'list' ? (
                  <ResultsList
                    rows={ready.rows}
                    layout={ready.layout}
                    selectedId={selectedId}
                    onOpen={onOpenPair}
                    onDownloadPdf={onDownloadPdf}
                  />
                ) : (
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
                )}
              </motion.div>
            </AnimatePresence>
          </section>

          {ready.names.length > 2 && (
            <SimilarityIndexPanel indices={result.similarity_indices} breakdowns={result.source_breakdowns} />
          )}
        </>
        )
      )}
    </div>
  )
}
