import { useEffect, useState } from 'react'
import { getModes } from './api/client'
import type { Mode } from './api/types'
import { AIDetectionResults } from './components/AIDetectionResults'
import { ComparisonInspector } from './components/ComparisonInspector'
import { DropZone } from './components/DropZone'
import { EmptyState } from './components/EmptyState'
import { HeatmapGrid } from './components/HeatmapGrid'
import { ModeBar } from './components/ModeBar'
import { SkeletonLoader } from './components/SkeletonLoader'
import { useScan } from './hooks/useScan'
import './styles/app.css'
import darkModeLogo from './assets/darkModeLogo.png'
import lightModeLogo from './assets/lightModeLogo.png'

interface SelectedPair {
  fileA: string
  fileB: string
  score: number
}

function App() {
  const [files, setFiles] = useState<File[]>([])
  const [modes, setModes] = useState<Mode[]>([])
  const [mode, setMode] = useState<Mode>('text_similarity')
  const [threshold, setThreshold] = useState(0.7)
  const [selectedPair, setSelectedPair] = useState<SelectedPair | null>(null)
  const [theme, setTheme] = useState<'light' | 'dark'>('light')

  useEffect(() => {
    // Sync theme with HTML data-theme attribute
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))
  }
  const { state, start, reset } = useScan()

  useEffect(() => {
    getModes()
      .then((list) => {
        setModes(list)
        setMode((current) => (list.includes(current) ? current : (list[0] ?? current)))
      })
      .catch(() => setModes(['code_similarity', 'text_similarity', 'ai_code', 'ai_text']))
  }, [])

  const isBusy = state.status === 'uploading' || state.status === 'processing'
  // Similarity requires 2 files, AI check requires 1+
  const isAiMode = mode === 'ai_code' || mode === 'ai_text'
  const minFiles = isAiMode ? 1 : 2
  const canScan = files.length >= minFiles && !isBusy

  const handleScan = () => {
    if (!canScan) return
    start(files, mode, threshold)
  }

  const handleReset = () => {
    setFiles([])
    setSelectedPair(null)
    reset()
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-inner" style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            {theme === 'dark' ? (
              <img src={darkModeLogo} alt="PlagCheck Logo" style={{ height: '40px' }} />
            ) : (
              <img src={lightModeLogo} alt="PlagCheck Logo" style={{ height: '40px' }} />
            )}
            <div>
              <p className="app-tagline">Local-execution similarity &amp; AI detection</p>
            </div>
          </div>
          <button 
            type="button" 
            className="btn btn-ghost" 
            onClick={toggleTheme}
            aria-label="Toggle theme"
            style={{ fontSize: '1.25rem', padding: '0.25rem 0.5rem' }}
          >
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
        </div>
      </header>

      <main className="app-main">
        {state.status !== 'ready' && (
          <section className="panel">
            <DropZone files={files} onFilesChange={setFiles} disabled={isBusy} mode={mode} />

            <ModeBar
              modes={modes}
              mode={mode}
              onModeChange={setMode}
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
              <SkeletonLoader label="Computing results…" sublabel={`Mode: ${mode}`} />
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
                description={`Drop ${isAiMode ? '1' : '2'}–50 supported files above to check.`}
              />
            )}
            
            {files.length === 1 && state.status === 'idle' && !isAiMode && (
              <EmptyState
                icon="⚠"
                title="Need another file"
                description="Similarity scans require at least 2 files to compare."
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
                  Mode: {state.result.mode} &middot; threshold: {state.result.threshold.toFixed(2)}
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

            {/* AI RESULTS */}
            {(state.result.mode === 'ai_code' || state.result.mode === 'ai_text') ? (
              <AIDetectionResults scores={state.result.ai_scores} />
            ) : (
              /* SIMILARITY RESULTS */
              state.result.matrix?.names.length ? (
                <>
                  <p className="app-tagline" style={{ marginTop: '0.5rem', marginBottom: '1rem' }}>
                    {state.result.pairs.filter((p) => p.flagged).length} of {state.result.pairs.length} pairs flagged
                  </p>
                  <HeatmapGrid
                    names={state.result.matrix.names}
                    scores={state.result.matrix.scores}
                    threshold={state.result.threshold}
                    onCellClick={(fileA, fileB, score) => setSelectedPair({ fileA, fileB, score })}
                  />
                </>
              ) : (
                <EmptyState title="No comparable files" description="Every uploaded file was rejected." />
              )
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
