import { AnimatePresence, motion } from 'motion/react'
import type { Mode, SamplePreset } from '../../api/types'
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
  disabled?: boolean
  threshold: number
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

export function ResultsCanvas({
  state,
  model,
  mode,
  disabled,
  threshold,
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
      <motion.div key={key} className="canvas-frame" {...panelMotion}>
        {state.status === 'idle' && <IdleState mode={mode} disabled={disabled} onRunSample={onRunSample} />}

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
