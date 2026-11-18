import { AnimatePresence } from 'motion/react'
import { useEffect, useEffectEvent, useMemo, useState } from 'react'
import { downloadFile, exportUrls } from './api/client'
import type { Algorithm, CheckResponse, Mode, SamplePreset } from './api/types'
import { DropZone } from './components/DropZone/DropZone'
import { DEFAULT_MIN_MATCH_WORDS, keptFiles } from './components/DropZone/rules'
import { Header } from './components/Header'
import { HistoryDrawer } from './components/HistoryDrawer'
import { ComparisonInspector } from './components/inspector/ComparisonInspector'
import type { ExportKind } from './components/results/ExportMenu'
import { ResultsCanvas } from './components/results/ResultsCanvas'
import { RunBar } from './components/RunBar'
import type { RunPhase } from './components/RunBar'
import { ScanSettings } from './components/ScanSettings'
import { Segmented } from './components/Segmented'
import { useApiStatus } from './hooks/useApiStatus'
import { useScan } from './hooks/useScan'
import { useTheme } from './hooks/useTheme'
import { useToast } from './hooks/useToast'
import { deriveResults } from './lib/deriveResults'
import type { ResultRow, Workspace } from './lib/deriveResults'
import { stem } from './lib/format'

const DEFAULT_THRESHOLD = 0.7

const WORKSPACE_OPTIONS: readonly { value: Workspace; label: string }[] = [
  { value: 'one-to-many', label: 'One vs many' },
  { value: 'batch', label: 'Batch' },
]

const EXPORT_NAMES: Record<ExportKind, string> = {
  pdf: 'Similarity Report.pdf',
  xlsx: 'Similarity Workbook.xlsx',
  heatmap: 'Similarity Heatmap.png',
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
  const [excludedTerms, setExcludedTerms] = useState<string[]>([])
  const [useDefaultExclusions, setUseDefaultExclusions] = useState(true)
  const [lastSamplePreset, setLastSamplePreset] = useState<SamplePreset | null>(null)
  const [runSignature, setRunSignature] = useState('')
  const [selected, setSelected] = useState<ResultRow | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [exportBusy, setExportBusy] = useState<ExportKind | null>(null)

  const { state, start, startSample, open, reset } = useScan()
  const { theme, toggleTheme } = useTheme()
  const { status: apiStatus, retry: retryStatus } = useApiStatus()
  const toast = useToast()

  const busy = state.status === 'uploading' || state.status === 'processing' || state.status === 'loading'
  const result = state.status === 'ready' ? state.result : null
  const files = workspace === 'one-to-many' ? [...reference, ...candidates] : batch
  const hasZipInBatch = workspace === 'batch' && batch.some((f) => f.name.toLowerCase().endsWith('.zip'))

  const blockedReason = (() => {
    if (apiStatus.state === 'offline') return 'Server unreachable'
    if (workspace === 'batch') {
      return batch.length < 2 && !hasZipInBatch ? 'Add at least 2 files' : null
    }
    if (reference.length === 0) return 'Add reference file'
    if (candidates.length === 0) return 'Add comparison files'
    return null
  })()

  const model = useMemo(
    () =>
      state.status === 'ready'
        ? deriveResults(state.result, state.meta.layout, threshold, state.meta.referenceName)
        : null,
    [state, threshold],
  )

  const currentExclSig = `${useDefaultExclusions ? '1' : '0'}:${excludedTerms.join(',')}`
  const settingsChanged =
    state.status === 'ready' &&
    (state.meta.source === 'scan' || state.meta.source === 'sample') &&
    (state.result.mode !== mode ||
      state.result.algorithm !== algorithm ||
      state.result.min_match_words !== minMatchWords ||
      (runSignature !== '' && runSignature !== currentExclSig))

  const syncLoadedScan = (scan: CheckResponse) => {
    if (scan.mode !== mode) {
      setMode(scan.mode)
    }
    setAlgorithm(scan.algorithm)
    setThreshold(scan.threshold)
    setMinMatchWords(scan.min_match_words)
  }

  const handleModeChange = (next: Mode) => {
    if (next === mode) return
    setMode(next)
    setAlgorithm('auto')
    const setAside = [reference, candidates, batch].reduce((n, list) => n + keptFiles(list, next).skipped, 0)
    setReference((list) => keptFiles(list, next).kept)
    setCandidates((list) => keptFiles(list, next).kept)
    setBatch((list) => keptFiles(list, next).kept)
    if (setAside > 0) {
      toast.show(`${setAside} incompatible ${setAside === 1 ? 'file' : 'files'} removed.`, 'error')
    }
  }

  const handleWorkspaceChange = (next: Workspace) => {
    setWorkspace(next)
  }

  const runScan = () => {
    if (busy) return
    if (state.status === 'ready' && state.meta.source === 'sample' && lastSamplePreset) {
      runSample(lastSamplePreset)
      return
    }
    if (blockedReason) return
    setSelected(null)
    setRunSignature(currentExclSig)
    start(
      { files, mode, threshold, algorithm, minMatchWords, excludedTerms, useDefaultExclusions },
      { layout: workspace, referenceName: reference[0]?.name },
    )
  }

  const runSample = (preset: SamplePreset) => {
    if (busy || apiStatus.state === 'offline') {
      if (apiStatus.state === 'offline') toast.show('Start the local API server first.', 'error')
      return
    }
    const targetMode: Mode = preset === 'code' ? 'code_similarity' : 'text_similarity'
    setWorkspace('batch')
    if (targetMode !== mode) {
      setMode(targetMode)
      setAlgorithm('auto')
    }
    setLastSamplePreset(preset)
    setSelected(null)
    setRunSignature(currentExclSig)
    startSample(
      {
        preset,
        threshold,
        algorithm: targetMode !== mode ? 'auto' : algorithm,
        minMatchWords,
        excludedTerms,
        useDefaultExclusions,
      },
      syncLoadedScan,
    )
  }

  const handleReset = () => {
    setSelected(null)
    setLastSamplePreset(null)
    reset()
  }

  const handleClearFiles = () => {
    if (workspace === 'one-to-many') {
      setReference([])
      setCandidates([])
    } else {
      setBatch([])
    }
  }

  const onShortcut =useEffectEvent((e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      runScan()
    }
  })
  useEffect(() => {
    window.addEventListener('keydown', onShortcut)
    return () => window.removeEventListener('keydown', onShortcut)
  }, [])

  useEffect(() => {
    if (state.status !== 'ready' || !window.matchMedia('(max-width: 1024px)').matches) return
    document.getElementById('results')?.scrollIntoView({ block: 'start' })
  }, [state.status])

  const saveExport = (kind: ExportKind) => {
    if (!result) return
    const scanId = result.scan_id
    const url =
      kind === 'xlsx'
        ? exportUrls.xlsx(scanId)
        : kind === 'pdf'
          ? exportUrls.pdf(scanId)
          : exportUrls.heatmap(scanId, model?.kind === 'ready' ? model.reference : undefined)
    setExportBusy(kind)
    downloadFile(url, EXPORT_NAMES[kind])
      .catch((err: unknown) => toast.show(err instanceof Error ? err.message : 'Export failed.', 'error'))
      .finally(() => setExportBusy(null))
  }

  const savePairPdf = (row: ResultRow) => {
    if (!result) return
    downloadFile(exportUrls.pairPdf(result.scan_id, row.fileA, row.fileB), `Comparison - ${stem(row.fileA)} vs ${stem(row.fileB)}.pdf`).catch(
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
    <div className="app-shell">
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
        <h1 className="visually-hidden">PlagCheck</h1>

        <div className="workspace" id="workspace-panel">
          <aside className="sidebar" aria-label="Scan setup">
            <div className="sidebar-scroll">
              <section className="panel">
                <div className="sidebar-mode-row">
                  <Segmented
                    id="workspace-mode"
                    label="Comparison mode"
                    size="sm"
                    options={WORKSPACE_OPTIONS}
                    value={workspace}
                    onChange={handleWorkspaceChange}
                    disabled={busy}
                  />
                </div>

                {workspace === 'one-to-many' ? (
                  <>
                    <DropZone
                      label="Reference File"
                      files={reference}
                      onFilesChange={setReference}
                      mode={mode}
                      maxFiles={1}
                      disabled={busy}
                    />
                    <DropZone
                      label="File to be Checked"
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
                    files={batch}
                    onFilesChange={setBatch}
                    mode={mode}
                    disabled={busy}
                  />
                )}

                {files.length > 0 && (
                  <div className="sidebar-files-foot">
                    <span className="sidebar-files-count num">
                      {files.length} {files.length === 1 ? 'file' : 'files'} staged
                    </span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={handleClearFiles}
                      disabled={busy}
                    >
                      Clear files
                    </button>
                  </div>
                )}
              </section>

              <section className="panel">
                <ScanSettings
                  mode={mode}
                  algorithm={algorithm}
                  onAlgorithmChange={setAlgorithm}
                  threshold={threshold}
                  onThresholdChange={setThreshold}
                  minMatchWords={minMatchWords}
                  onMinMatchWordsChange={setMinMatchWords}
                  excludedTerms={excludedTerms}
                  onExcludedTermsChange={setExcludedTerms}
                  useDefaultExclusions={useDefaultExclusions}
                  onUseDefaultExclusionsChange={setUseDefaultExclusions}
                  disabled={busy}
                />
              </section>
            </div>

            <RunBar run={run} blockedReason={busy ? null : blockedReason} onRun={runScan} onCancel={handleReset} />
          </aside>

          <section id="results" className="canvas" aria-label="Results">
            <ResultsCanvas
              state={state}
              model={model}
              mode={mode}
              disabled={busy}
              threshold={threshold}
              settingsChanged={settingsChanged}
              selectedId={selected?.id ?? null}
              exportBusy={exportBusy}
              onThresholdChange={setThreshold}
              onRunSample={runSample}
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
              setWorkspace('batch')
              open(scanId, syncLoadedScan)
            }}
            onDeleted={(scanId) => {
              if (result?.scan_id === scanId) handleReset()
            }}
            onClose={() => setHistoryOpen(false)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

export default App
