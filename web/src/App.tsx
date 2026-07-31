import { useEffect, useState } from 'react'
import type { Algorithm, Mode } from './api/types'
import { ComparisonInspector } from './components/ComparisonInspector'
import { DropZone } from './components/DropZone'
import { EmptyState } from './components/EmptyState'
import { HeatmapGrid } from './components/HeatmapGrid'
import { ScanSettings } from './components/ScanSettings'
import { Sidebar } from './components/Sidebar'
import { SimilarityIndexPanel } from './components/SimilarityIndexPanel'
import { SkeletonLoader } from './components/SkeletonLoader'
import { useScan } from './hooks/useScan'
import './styles/app.css'

interface SelectedPair {
  fileA: string
  fileB: string
  score: number
}

const MODE_TITLES: Record<Mode, string> = {
  text_similarity: 'Text Similarity Check',
  code_similarity: 'Code Similarity Check',
}

const MODE_TAGLINES: Record<Mode, string> = {
  text_similarity: 'Compare prose documents for overlapping or copied passages.',
  code_similarity: 'Compare source files for structural and copy-paste similarity.',
}

function App() {
  const [files, setFiles] = useState<File[]>([])
  const [mode, setMode] = useState<Mode>('text_similarity')
  const [algorithm, setAlgorithm] = useState<Algorithm>('auto')
  const [threshold, setThreshold] = useState(0.7)
  const [minMatchWords, setMinMatchWords] = useState(8)
  const [selectedPair, setSelectedPair] = useState<SelectedPair | null>(null)

  const { state, start, reset } = useScan()

  const isBusy = state.status === 'uploading' || state.status === 'processing'
  // A single file is always accepted (it just has no pairs), but a scan is
  // only useful with at least one uploaded file.
  const canScan = files.length >= 1 && !isBusy

  const handleModeChange = (next: Mode) => {
    setMode(next)
    setAlgorithm('auto')
    setFiles([])
    setSelectedPair(null)
    reset()
  }

  const handleScan = () => {
    if (!canScan) return
    setSelectedPair(null)
    start({ files, mode, threshold, algorithm, minMatchWords })
  }

  const handleReset = () => {
    setFiles([])
    setSelectedPair(null)
    reset()
  }

  return (
    <div className="app-shell">
      <Sidebar
        mode={mode}
        onModeChange={handleModeChange}
        disabled={isBusy}
      />

      <div className="content">
        <header className="content-head">
          <div>
            <h1>{MODE_TITLES[mode]}</h1>
            <p className="app-tagline">{MODE_TAGLINES[mode]}</p>
          </div>
          {state.status === 'ready' ? (
            <button type="button" className="btn btn-secondary" onClick={handleReset}>
              New scan
            </button>
          ) : (
            <button type="button" className="btn btn-primary" disabled={!canScan} onClick={handleScan}>
              {isBusy ? 'Scanning…' : '▶ Run Scan'}
            </button>
          )}
        </header>

        {state.status === 'uploading' && (
          <div className="upload-progress" role="progressbar" aria-valuenow={Math.round(state.progress * 100)}>
            <div className="upload-progress-bar" style={{ width: `${state.progress * 100}%` }} />
            <span>Uploading… {Math.round(state.progress * 100)}%</span>
          </div>
        )}

        {state.status === 'processing' && (
          <SkeletonLoader label="Computing results…" sublabel={`Mode: ${mode}`} />
        )}

        {state.status === 'error' && (
          <div className="error-banner" role="alert">
            <strong>Scan failed.</strong> {state.message}
          </div>
        )}

        <div className="content-columns">
          <div className="content-column-left">
            <ScanSettings
              mode={mode}
              algorithm={algorithm}
              onAlgorithmChange={setAlgorithm}
              threshold={threshold}
              onThresholdChange={setThreshold}
              minMatchWords={minMatchWords}
              onMinMatchWordsChange={setMinMatchWords}
              disabled={isBusy}
            />
            <DropZone files={files} onFilesChange={setFiles} disabled={isBusy} mode={mode} />

            {files.length === 0 && state.status === 'idle' && (
              <EmptyState
                icon="⇪"
                title="No files yet"
                description="Add 1–50 supported files to check."
              />
            )}
          </div>

          <div className="content-column-right">
            {state.status !== 'ready' && (
              <EmptyState title="No results yet" description="Run a scan to see the similarity matrix." />
            )}

            {state.status === 'ready' && (
              <>
                {state.result.errors.length > 0 && (
                  <ul className="dropzone-rejections">
                    {state.result.errors.map((e) => (
                      <li key={e.file}>
                        <strong>{e.file}</strong> — {e.error}
                      </li>
                    ))}
                  </ul>
                )}

                {state.result.matrix?.names.length ? (
                  <>
                    <SimilarityIndexPanel
                      similarityIndices={state.result.similarity_indices}
                      sourceBreakdowns={state.result.source_breakdowns}
                      onSourceClick={(fileA, fileB, score) => setSelectedPair({ fileA, fileB, score })}
                    />

                    <div className="card">
                      <div className="card-head">
                        <span className="card-title">Similarity Matrix</span>
                        <span className="card-flagged-badge">
                          <span className="card-flagged-dot" aria-hidden="true" />
                          {state.result.pairs.filter((p) => p.flagged).length} flagged
                        </span>
                      </div>
                      <HeatmapGrid
                        names={state.result.matrix.names}
                        scores={state.result.matrix.scores}
                        threshold={state.result.threshold}
                        onCellClick={(fileA, fileB, score) => setSelectedPair({ fileA, fileB, score })}
                      />
                    </div>

                    {selectedPair && (
                      <ComparisonInspector
                        scanId={state.result.scan_id}
                        fileA={selectedPair.fileA}
                        fileB={selectedPair.fileB}
                        score={selectedPair.score}
                        onClose={() => setSelectedPair(null)}
                      />
                    )}
                  </>
                ) : (
                  <EmptyState title="No comparable files" description="Every uploaded file was rejected." />
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
