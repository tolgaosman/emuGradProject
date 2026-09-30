import { AnimatePresence } from 'motion/react'
import { useEffect, useEffectEvent, useMemo, useState } from 'react'
import { downloadFile, exportUrls } from './api/client'
import type { Algorithm, Mode } from './api/types'
import { DropZone } from './components/DropZone/DropZone'
import { Header } from './components/Header'
import { HistoryDrawer } from './components/HistoryDrawer'
import { ComparisonInspector } from './components/inspector/ComparisonInspector'
import type { ExportKind } from './components/results/ExportMenu'
import { ResultsCanvas } from './components/results/ResultsCanvas'
import { RunBar } from './components/RunBar'
import type { RunPhase } from './components/RunBar'
import { ScanSettings } from './components/ScanSettings'
import { WorkspaceTabs } from './components/WorkspaceTabs'
import { useApiStatus } from './hooks/useApiStatus'
import { useScan } from './hooks/useScan'
import { useTheme } from './hooks/useTheme'
import { useToast } from './hooks/useToast'
import { deriveResults } from './lib/deriveResults'
import type { ResultRow, Workspace } from './lib/deriveResults'
import { stem } from './lib/format'

const DEFAULT_THRESHOLD = 0.7
const DEFAULT_MIN_MATCH_WORDS = 8

const EXPORT_NAMES: Record<ExportKind, string> = {
  html: 'plagcheck-report.html',
  csv: 'plagcheck-matrix.csv',
  heatmap: 'plagcheck-heatmap.png',
}

function App() {
  const [mode, setMode] = useState<Mode>('text_similarity')
  const [workspace, setWorkspace] = useState<Workspace>('one-to-many')
  const [reference, setReference] = useState<File[]>([])
  const [candidates, setCandidates] = useState<File[]>([])
  const [batch, setBatch] = useState<File[]>([])
  const [algorithm, setAlgorithm] = useState<Algorithm>('auto')
  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD)
  const [minMatchWords, setMinMatchWords] = useState(DEFAULT_MIN_MATCH_WORDS)
  const [selected, setSelected] = useState<ResultRow | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [exportBusy, setExportBusy] = useState<ExportKind | null>(null)

  const { state, start, open, reset } = useScan()
  const { theme, toggleTheme } = useTheme()
  const { status: apiStatus, retry: retryStatus } = useApiStatus()
  const toast = useToast()

  const busy = state.status === 'uploading' || state.status === 'processing' || state.status === 'loading'
  const result = state.status === 'ready' ? state.result : null
  const files = workspace === 'one-to-many' ? [...reference, ...candidates] : batch

  const blockedReason = (() => {
    if (apiStatus.state === 'offline') return 'The PlagCheck server is unreachable.'
    if (workspace === 'batch') return batch.length < 2 ? 'Add at least two documents to compare.' : null
    if (reference.length === 0) return 'Add the document you want to check.'
    if (candidates.length === 0) return 'Add at least one document to compare it with.'
    return null
  })()

  const model = useMemo(
    () =>
      state.status === 'ready'
        ? deriveResults(state.result, state.meta.layout, threshold, state.meta.referenceName)
        : null,
    [state, threshold],
  )

  const settingsChanged =
    state.status === 'ready' &&
    state.meta.source === 'scan' &&
    (state.result.mode !== mode || state.result.algorithm !== algorithm || state.result.min_match_words !== minMatchWords)

  const clearStaged = () => {
    setReference([])
    setCandidates([])
    setBatch([])
  }

  const handleModeChange = (next: Mode) => {
    if (next === mode) return
    setMode(next)
    setAlgorithm('auto')
    // Mod değişince dosyaları ve ekrandaki sonuçları silme!
  }

  const handleWorkspaceChange = (next: Workspace) => {
    setWorkspace(next)
    setSelected(null)
    reset()
  }

  const runScan = () => {
    if (blockedReason || busy) return
    setSelected(null)
    start(
      { files, mode, threshold, algorithm, minMatchWords },
      { layout: workspace, referenceName: reference[0]?.name },
    )
  }

  const handleReset = () => {
    setSelected(null)
    reset()
  }

  const onShortcut = useEffectEvent((e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      runScan()
    }
  })
  useEffect(() => {
    window.addEventListener('keydown', onShortcut)
    return () => window.removeEventListener('keydown', onShortcut)
  }, [])

  // A reopened scan brings its own settings; mirror them so the controls
  // describe what's on screen.
  const reopened = state.status === 'ready' && state.meta.source === 'history' ? state.result : null
  const adoptSettings = useEffectEvent((scan: NonNullable<typeof reopened>) => {
    if (scan.mode !== mode) {
      clearStaged()
      setMode(scan.mode)
    }
    setAlgorithm(scan.algorithm)
    setThreshold(scan.threshold)
    setMinMatchWords(scan.min_match_words)
  })
  useEffect(() => {
    if (reopened) adoptSettings(reopened)
  }, [reopened])

  // On stacked (narrow) layouts, bring fresh results into view.
  useEffect(() => {
    if (state.status !== 'ready' || !window.matchMedia('(max-width: 1024px)').matches) return
    document.getElementById('results')?.scrollIntoView({ block: 'start' })
  }, [state.status])

  const saveExport = (kind: ExportKind) => {
    if (!result) return
    const scanId = result.scan_id
    const url =
      kind === 'csv'
        ? exportUrls.csv(scanId)
        : kind === 'html'
          ? exportUrls.html(scanId)
          : exportUrls.heatmap(scanId, model?.kind === 'ready' ? model.reference : undefined)
    setExportBusy(kind)
    downloadFile(url, EXPORT_NAMES[kind])
      .catch((err: unknown) => toast.show(err instanceof Error ? err.message : 'Export failed.', 'error'))
      .finally(() => setExportBusy(null))
  }

  const savePairPdf = (row: ResultRow) => {
    if (!result) return
    downloadFile(exportUrls.pairPdf(result.scan_id, row.fileA, row.fileB), `${stem(row.fileA)} vs ${stem(row.fileB)}.pdf`).catch(
      (err: unknown) => toast.show(err instanceof Error ? err.message : 'PDF export failed.', 'error'),
    )
  }

  const run: RunPhase =
    state.status === 'uploading'
      ? { phase: 'uploading', progress: state.progress }
      : state.status === 'processing'
        ? { phase: 'processing' }
        : { phase: 'ready' }

  return (
    <>
      <Header
        mode={mode}
        onModeChange={handleModeChange}
        modeLocked={busy}
        theme={theme}
        onToggleTheme={toggleTheme}
        apiStatus={apiStatus}
        onRetryStatus={retryStatus}
        onOpenHistory={() => setHistoryOpen(true)}
      />

      <main className="page">
        <h1 className="visually-hidden">PlagCheck — plagiarism and file similarity detection</h1>
        <WorkspaceTabs value={workspace} onChange={handleWorkspaceChange} disabled={busy} />

        <div className="workspace" id="workspace-panel" role="tabpanel" aria-labelledby={`workspace-tab-${workspace}`}>
          <aside className="sidebar" aria-label="Scan setup">
            <section className="panel" aria-labelledby="documents-title">
              <h2 id="documents-title" className="panel-title">
                <span className="panel-step num">1</span>
                Documents
              </h2>
              {workspace === 'one-to-many' ? (
                <>
                  <DropZone
                    label="Check this document"
                    files={reference}
                    onFilesChange={setReference}
                    mode={mode}
                    maxFiles={1}
                    disabled={busy}
                  />
                  <DropZone
                    label="Against these"
                    files={candidates}
                    onFilesChange={setCandidates}
                    mode={mode}
                    maxFiles={49}
                    disabled={busy}
                  />
                </>
              ) : (
                <DropZone
                  label="Submissions"
                  description="Every file is compared with every other."
                  files={batch}
                  onFilesChange={setBatch}
                  mode={mode}
                  disabled={busy}
                />
              )}
            </section>

            <section className="panel" aria-labelledby="settings-title">
              <h2 id="settings-title" className="panel-title">
                <span className="panel-step num">2</span>
                Review settings
              </h2>
              <ScanSettings
                mode={mode}
                algorithm={algorithm}
                onAlgorithmChange={setAlgorithm}
                threshold={threshold}
                onThresholdChange={setThreshold}
                minMatchWords={minMatchWords}
                onMinMatchWordsChange={setMinMatchWords}
                disabled={busy}
              />
            </section>

            <RunBar run={run} blockedReason={busy ? null : blockedReason} onRun={runScan} onCancel={handleReset} />
          </aside>

          <section id="results" className="canvas" aria-label="Results">
            <ResultsCanvas
              state={state}
              model={model}
              mode={mode}
              workspace={workspace}
              threshold={threshold}
              settingsChanged={settingsChanged}
              selectedId={selected?.id ?? null}
              exportBusy={exportBusy}
              onOpenPair={setSelected}
              onDownloadPdf={savePairPdf}
              onExport={saveExport}
              onRerun={runScan}
              onReset={handleReset}
            />
          </section>
        </div>
      </main>

      <AnimatePresence>
        {selected && result && model?.kind === 'ready' && (
          <ComparisonInspector
            key="inspector"
            scanId={result.scan_id}
            row={selected}
            rows={model.rows}
            mode={result.mode}
            algorithm={result.algorithm}
            onNavigate={setSelected}
            onDownloadPdf={savePairPdf}
            onClose={() => setSelected(null)}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {historyOpen && (
          <HistoryDrawer
            key="history"
            currentScanId={result?.scan_id ?? null}
            onOpenScan={(scanId) => {
              setHistoryOpen(false)
              setSelected(null)
              open(scanId)
            }}
            onDeleted={(scanId) => {
              if (result?.scan_id === scanId) handleReset()
            }}
            onClose={() => setHistoryOpen(false)}
          />
        )}
      </AnimatePresence>
    </>
  )
}

export default App
