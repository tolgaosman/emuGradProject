import { useState } from 'react'
import { heatmapUrl } from './api/client'
import type { Algorithm, Mode } from './api/types'
import { ComparisonInspector } from './components/ComparisonInspector'
import { DropZone } from './components/DropZone'
import { EmptyState } from './components/EmptyState'
import { HeatmapGrid } from './components/HeatmapGrid'
import { ScanSettings } from './components/ScanSettings'
import { SimilarityReport } from './components/SimilarityReport'
import { SkeletonLoader } from './components/SkeletonLoader'
import { TopBar } from './components/TopBar'
import { useScan } from './hooks/useScan'
import { useTheme } from './hooks/useTheme'
import './styles/app.css'

interface SelectedPair {
  fileA: string
  fileB: string
  score: number
}

function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3v12m0 0 4.5-4.5M12 15l-4.5-4.5M4 19h16"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function RefreshIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M20 11A8 8 0 1 0 18.5 16"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M20 5v6h-6"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  )
}

function App() {
  const [referenceFile, setReferenceFile] = useState<File | null>(null)
  const [candidateFiles, setCandidateFiles] = useState<File[]>([])
  const [mode, setMode] = useState<Mode>('text_similarity')
  const [algorithm, setAlgorithm] = useState<Algorithm>('auto')
  const [threshold, setThreshold] = useState(0.7)
  const [minMatchWords, setMinMatchWords] = useState(8)
  const [selectedPair, setSelectedPair] = useState<SelectedPair | null>(null)

  const { state, start, reset } = useScan()
  const { theme, toggleTheme } = useTheme()

  const isBusy = state.status === 'uploading' || state.status === 'processing'
  // A scan needs exactly one reference file plus at least one candidate to
  // check against it.
  const canScan = referenceFile !== null && candidateFiles.length >= 1 && !isBusy

  const handleModeChange = (next: Mode) => {
    setMode(next)
    setAlgorithm('auto')
    setReferenceFile(null)
    setCandidateFiles([])
    setSelectedPair(null)
    reset()
  }

  const handleScan = () => {
    if (!referenceFile || !canScan) return
    setSelectedPair(null)
    start({ files: [referenceFile, ...candidateFiles], mode, threshold, algorithm, minMatchWords })
  }

  const handleReset = () => {
    setReferenceFile(null)
    setCandidateFiles([])
    setSelectedPair(null)
    reset()
  }

  return (
    <div className="app-shell">
      <TopBar
        mode={mode}
        onModeChange={handleModeChange}
        disabled={isBusy}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <main className="content-columns">
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

          <DropZone
            title="Reference file"
            maxFiles={1}
            files={referenceFile ? [referenceFile] : []}
            onFilesChange={(next) => setReferenceFile(next[0] ?? null)}
            disabled={isBusy}
            mode={mode}
          />

          <DropZone
            title="Files to check"
            files={candidateFiles}
            onFilesChange={setCandidateFiles}
            disabled={isBusy}
            mode={mode}
          />

          <div className="run-bar">
            {state.status === 'ready' ? (
              <button type="button" className="btn btn-secondary btn-block" onClick={handleReset}>
                New scan
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary btn-block"
                disabled={!canScan}
                onClick={handleScan}
              >
                {isBusy ? 'Scanning…' : '▶ Run Scan'}
              </button>
            )}

            {state.status === 'uploading' && (
              <div
                className="upload-progress"
                role="progressbar"
                aria-label="Upload progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(state.progress * 100)}
              >
                <div className="upload-progress-bar" style={{ width: `${state.progress * 100}%` }} />
                <span>Uploading… {Math.round(state.progress * 100)}%</span>
              </div>
            )}

            {state.status === 'error' && (
              <div className="error-banner" role="alert">
                <strong>Scan failed.</strong> {state.message}
              </div>
            )}
          </div>
        </div>

        <div className="content-column-right">
          {state.status === 'processing' && (
            <SkeletonLoader label="Computing results…" sublabel={`Mode: ${mode}`} />
          )}

          {(state.status === 'idle' || state.status === 'uploading' || state.status === 'error') && (
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

              {(() => {
                const matrix = state.result.matrix
                const refName = referenceFile?.name
                const refIdx = matrix && refName ? matrix.names.indexOf(refName) : -1

                if (!matrix?.names.length) {
                  return (
                    <EmptyState title="No comparable files" description="Every uploaded file was rejected." />
                  )
                }

                // Candidates can load fine while the reference itself is
                // rejected (wrong extension for the mode, unreadable PDF).
                // Saying "every file was rejected" there would be wrong and
                // would hide which file actually needs attention.
                if (refIdx === -1) {
                  const refError = state.result.errors.find((e) => e.file === refName)
                  return (
                    <EmptyState
                      title="Reference file couldn't be processed"
                      description={
                        refError
                          ? `${refError.file} — ${refError.error}`
                          : 'The reference file was rejected, so there is nothing to compare against.'
                      }
                    />
                  )
                }

                const candidateNames = matrix.names.filter((_, i) => i !== refIdx)
                const candidateScores = matrix.names
                  .map((_, i) => i)
                  .filter((i) => i !== refIdx)
                  .map((i) => matrix.scores[refIdx]?.[i] ?? 0)
                const flaggedCount = state.result.pairs.filter(
                  (p) => p.flagged && (p.file_a === refName || p.file_b === refName),
                ).length

                return (
                  <>
                    <div className="card">
                      <div className="card-head">
                        <span className="card-title">Similarity Matrix</span>
                        <div className="card-head-actions">
                          <span className="card-flagged-badge">
                            <span className="card-flagged-dot" aria-hidden="true" />
                            {flaggedCount} flagged
                          </span>
                          <button
                            type="button"
                            className="icon-btn"
                            title="Re-run on the same staged files with the current threshold, algorithm and min match words"
                            aria-label="Re-run scan"
                            disabled={!canScan}
                            onClick={handleScan}
                          >
                            <RefreshIcon />
                          </button>
                          <a
                            className="icon-btn"
                            href={heatmapUrl(state.result.scan_id)}
                            download={`plagcheck-${state.result.scan_id}.png`}
                            title="Download the similarity heatmap as a PNG"
                            aria-label="Download heatmap"
                          >
                            <DownloadIcon />
                          </a>
                        </div>
                      </div>
                      <HeatmapGrid
                        referenceName={matrix.names[refIdx]}
                        candidateNames={candidateNames}
                        scores={candidateScores}
                        threshold={state.result.threshold}
                        onCellClick={(fileB, score) =>
                          setSelectedPair({ fileA: matrix.names[refIdx], fileB, score })
                        }
                      />
                    </div>

                    <SimilarityReport
                      referenceName={matrix.names[refIdx]}
                      names={matrix.names}
                      scores={matrix.scores}
                      threshold={state.result.threshold}
                      onSelectPair={(fileA, fileB, score) => setSelectedPair({ fileA, fileB, score })}
                    />

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
                )
              })()}
            </>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
