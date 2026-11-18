import { AnimatePresence, motion } from 'motion/react'
import type { Algorithm, Mode, SamplePreset } from '../../api/types'
import type { ScanState } from '../../hooks/useScan'
import type { ResultRow, ResultsModel } from '../../lib/deriveResults'
import { panelMotion } from '../../lib/motion'
import { ErrorState } from './ErrorState'
import type { ExportKind } from './ExportMenu'
import { IdleState } from './IdleState'
import { ProgressState } from './ProgressState'
import { ResultsView } from './ResultsView'

interface ResultsCanvasProps {
  state: ScanState
  model: ResultsModel | null
  mode: Mode
  algorithm: Algorithm
  threshold: number
  minMatchWords: number
  useDefaultExclusions: boolean
  excludedCount: number
  settingsChanged: boolean
  selectedId: string | null
  exportBusy: ExportKind | null
  onThresholdChange: (next: number) => void
  onRunSample: (preset: SamplePreset) => void
  onOpenPair: (row: ResultRow) => void
  onDownloadPdf: (row: ResultRow) => void
  onExport: (kind: ExportKind) => void
  onRerun: () => void
  onReset: () => void
}

/** The right-hand column: one view per scan state, cross-faded. */
export function ResultsCanvas({
  state,
  model,
  mode,
  algorithm,
  threshold,
  minMatchWords,
  useDefaultExclusions,
  excludedCount,
  settingsChanged,
  selectedId,
  exportBusy,
  onThresholdChange,
  onRunSample,
  onOpenPair,
  onDownloadPdf,
  onExport,
  onRerun,
  onReset,
}: ResultsCanvasProps) {
  const key = state.status === 'uploading' ? 'processing' : state.status

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div key={key} {...panelMotion}>
        {state.status === 'idle' && (
          <IdleState
            mode={mode}
            threshold={threshold}
            algorithm={algorithm}
            minMatchWords={minMatchWords}
            useDefaultExclusions={useDefaultExclusions}
            excludedCount={excludedCount}
            onRunSample={onRunSample}
          />
        )}

        {(state.status === 'uploading' || state.status === 'processing' || state.status === 'loading') && (
          <ProgressState phase={state.status} />
        )}

        {state.status === 'error' && (
          <ErrorState
            message={state.message}
            code={state.code}
            fileErrors={state.fileErrors}
            onRetry={state.meta.source === 'scan' ? onRerun : undefined}
            onDismiss={onReset}
          />
        )}

        {state.status === 'ready' && model && (
          <ResultsView
            result={state.result}
            model={model}
            threshold={threshold}
            source={state.meta.source}
            settingsChanged={settingsChanged}
            selectedId={selectedId}
            exportBusy={exportBusy}
            onThresholdChange={onThresholdChange}
            onOpenPair={onOpenPair}
            onDownloadPdf={onDownloadPdf}
            onExport={onExport}
            onRerun={onRerun}
            onNewScan={onReset}
          />
        )}
      </motion.div>
    </AnimatePresence>
  )
}
