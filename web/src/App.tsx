import { useEffect, useState } from 'react'
import { getAlgorithms } from './api/client'
import type { Algorithm } from './api/types'
import { AlgorithmBar } from './components/AlgorithmBar'
import { ComparisonInspector } from './components/ComparisonInspector'
import { DropZone } from './components/DropZone'
import { EmptyState } from './components/EmptyState'
import { HeatmapGrid } from './components/HeatmapGrid'
import { SkeletonLoader } from './components/SkeletonLoader'
import { useScan } from './hooks/useScan'
import './styles/app.css'

interface SelectedPair {
  fileA: string
  fileB: string
  score: number
}

function App() {
  const [files, setFiles] = useState<File[]>([])
  const [algorithms, setAlgorithms] = useState<Algorithm[]>([])
  const [algorithm, setAlgorithm] = useState<Algorithm>('cosine')
  const [threshold, setThreshold] = useState(0.7)
  const [selectedPair, setSelectedPair] = useState<SelectedPair | null>(null)
  const { state, start, reset } = useScan()

  useEffect(() => {
    getAlgorithms()
      .then((list) => {
        setAlgorithms(list)
        setAlgorithm((current) => (list.includes(current) ? current : (list[0] ?? current)))
      })
      .catch(() => setAlgorithms(['cosine', 'winnowing', 'jaccard', 'ast', 'all']))
  }, [])

  const isBusy = state.status === 'uploading' || state.status === 'processing'
  const canScan = files.length >= 2 && !isBusy

  const handleScan = () => {
    if (!canScan) return
    start(files, algorithm, threshold)
  }

  const handleReset = () => {
    setFiles([])
    setSelectedPair(null)
    reset()
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-inner">
          <span className="app-mark">◆</span>
          <div>
            <h1>PlagCheck</h1>
            <p className="app-tagline">Local-execution plagiarism &amp; similarity detection</p>
          </div>
        </div>
      </header>

      <main className="app-main">
        {state.status !== 'ready' && (
          <section className="panel">
            <DropZone files={files} onFilesChange={setFiles} disabled={isBusy} />

            <AlgorithmBar
              algorithms={algorithms}
              algorithm={algorithm}
              onAlgorithmChange={setAlgorithm}
              threshold={threshold}
              onThresholdChange={setThreshold}
              disabled={isBusy}
            />

            <div className="panel-actions">
              <button type="button" className="btn btn-primary" disabled={!canScan} onClick={handleScan}>
                {isBusy ? 'Scanning…' : `Scan ${files.length || ''} file${files.length === 1 ? '' : 's'}`}
              </button>
              {files.length > 0 && !isBusy && (
                <button type="button" className="btn btn-ghost" onClick={() => setFiles([])}>
                  Clear
                </button>
              )}
            </div>

            {state.status === 'uploading' && (
              <div
                className="upload-progress"
                role="progressbar"
                aria-valuenow={Math.round(state.progress * 100)}
              >
                <div className="upload-progress-bar" style={{ width: `${state.progress * 100}%` }} />
                <span>Uploading… {Math.round(state.progress * 100)}%</span>
              </div>
            )}

            {state.status === 'processing' && (
              <SkeletonLoader label="Computing similarities…" sublabel={`Algorithm: ${algorithm}`} />
            )}

            {state.status === 'error' && (
              <div className="error-banner" role="alert">
                <strong>Scan failed.</strong> {state.message}
              </div>
            )}

            {files.length === 0 && state.status === 'idle' && (
              <EmptyState
                icon="⇪"
                title="No files yet"
                description="Drop 2–50 supported files above to check for similarity."
              />
            )}
          </section>
        )}

        {state.status === 'ready' && (
          <section className="panel results-panel">
            <div className="results-header">
              <div>
                <h2>Results</h2>
                <p className="app-tagline">
                  {state.result.pairs.filter((p) => p.flagged).length} of {state.result.pairs.length} pairs
                  flagged &middot; algorithm: {state.result.algorithm} &middot; threshold:{' '}
                  {state.result.threshold.toFixed(2)}
                </p>
              </div>
              <button type="button" className="btn btn-secondary" onClick={handleReset}>
                New scan
              </button>
            </div>

            {state.result.errors.length > 0 && (
              <ul className="dropzone-rejections">
                {state.result.errors.map((e) => (
                  <li key={e.file}>
                    <strong>{e.file}</strong> — {e.error}
                  </li>
                ))}
              </ul>
            )}

            {state.result.matrix.names.length > 0 ? (
              <HeatmapGrid
                names={state.result.matrix.names}
                scores={state.result.matrix.scores}
                threshold={state.result.threshold}
                onCellClick={(fileA, fileB, score) => setSelectedPair({ fileA, fileB, score })}
              />
            ) : (
              <EmptyState title="No comparable files" description="Every uploaded file was rejected." />
            )}
          </section>
        )}
      </main>

      {selectedPair && state.status === 'ready' && (
        <ComparisonInspector
          scanId={state.result.scan_id}
          fileA={selectedPair.fileA}
          fileB={selectedPair.fileB}
          score={selectedPair.score}
          onClose={() => setSelectedPair(null)}
        />
      )}
    </div>
  )
}

export default App
