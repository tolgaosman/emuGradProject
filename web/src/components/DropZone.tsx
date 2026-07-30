import { useCallback, useId, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import type { Mode } from '../api/types'

const MAX_BYTES = 10 * 1024 * 1024
const MAX_FILES = 50

interface FileRejection {
  name: string
  reason: string
}

interface DropZoneProps {
  files: File[]
  onFilesChange: (files: File[]) => void
  disabled?: boolean
  mode?: Mode
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot === -1 ? '' : name.slice(dot).toLowerCase()
}

export function DropZone({ files, onFilesChange, disabled, mode }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [rejections, setRejections] = useState<FileRejection[]>([])
  const [activeTab, setActiveTab] = useState<'upload' | 'paste'>('upload')
  const [pastedText, setPastedText] = useState('')
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)

  const isTextMode = mode === 'ai_text' || mode === 'text_similarity'
  const supportedExtensions = isTextMode ? ['.txt', '.pdf', '.docx'] : ['.txt', '.py', '.pdf', '.docx']
  const extensionsDisplay = isTextMode ? '.txt · .pdf · .docx' : '.txt · .py · .pdf · .docx'

  const validate = useCallback((candidate: File[], existingCount: number): { accepted: File[]; rejections: FileRejection[] } => {
    const accepted: File[] = []
    const newRejections: FileRejection[] = []
    let count = existingCount

    for (const file of candidate) {
      if (!supportedExtensions.includes(extensionOf(file.name))) {
        newRejections.push({ name: file.name, reason: 'Unsupported format for selected mode' })
        continue
      }
      if (file.size === 0) {
        newRejections.push({ name: file.name, reason: 'File is empty' })
        continue
      }
      if (file.size > MAX_BYTES) {
        newRejections.push({ name: file.name, reason: 'Exceeds 10 MB limit' })
        continue
      }
      if (count >= MAX_FILES) {
        newRejections.push({ name: file.name, reason: `Batch limit of ${MAX_FILES} files reached` })
        continue
      }
      accepted.push(file)
      count += 1
    }

    return { accepted, rejections: newRejections }
  }, [supportedExtensions])

  const addFiles = useCallback(
    (incoming: FileList | File[]) => {
      const { accepted, rejections: newRejections } = validate(Array.from(incoming), files.length)
      if (accepted.length > 0) onFilesChange([...files, ...accepted])
      setRejections(newRejections)
    },
    [files, onFilesChange, validate],
  )

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    if (disabled) return
    addFiles(e.dataTransfer.files)
  }

  const removeFile = (index: number) => {
    const next = [...files]
    next.splice(index, 1)
    onFilesChange(next)
  }

  const handlePasteSubmit = () => {
    if (!pastedText.trim()) return
    const file = new File([pastedText], `pasted_text_${files.length + 1}.txt`, { type: 'text/plain' })
    addFiles([file])
    setPastedText('')
    setActiveTab('upload')
  }

  return (
    <div className="dropzone-wrap">
      <div className="dropzone-tabs" style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
        <button
          type="button"
          className={`btn ${activeTab === 'upload' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveTab('upload')}
          disabled={disabled}
        >
          Upload Files
        </button>
        <button
          type="button"
          className={`btn ${activeTab === 'paste' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveTab('paste')}
          disabled={disabled}
        >
          Paste Text
        </button>
      </div>

      {activeTab === 'upload' ? (
        <div
          className={`dropzone${isDragging ? ' dropzone-active' : ''}${disabled ? ' dropzone-disabled' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            if (!disabled) setIsDragging(true)
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
        >
          <label htmlFor={inputId} className="dropzone-label">
            <div className="dropzone-icon" aria-hidden="true">
              ⇪
            </div>
            <p className="dropzone-title">Drop files to compare</p>
            <p className="dropzone-hint">
              {extensionsDisplay} — up to 10 MB each, {MAX_FILES} files max
            </p>
            <span className="btn btn-secondary dropzone-browse">Browse files</span>
          </label>
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            multiple
            accept={supportedExtensions.join(',')}
            disabled={disabled}
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files)
              e.target.value = ''
            }}
          />
        </div>
      ) : (
        <div className="paste-area">
          <textarea
            value={pastedText}
            onChange={(e) => setPastedText(e.target.value)}
            disabled={disabled}
            placeholder="Paste your text here (up to 15,000 characters)..."
            maxLength={15000}
            style={{
              width: '100%',
              minHeight: '200px',
              padding: '1rem',
              borderRadius: '8px',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text)',
              fontFamily: 'inherit',
              resize: 'vertical',
              marginBottom: '1rem'
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              {pastedText.length} / 15,000 characters
            </span>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handlePasteSubmit}
              disabled={disabled || !pastedText.trim()}
            >
              Add as Text File
            </button>
          </div>
        </div>
      )}

      {rejections.length > 0 && (
        <ul className="dropzone-rejections" role="alert">
          {rejections.map((r, i) => (
            <li key={`${r.name}-${i}`}>
              <strong>{r.name}</strong> — {r.reason}
            </li>
          ))}
        </ul>
      )}

      {files.length > 0 && (
        <ul className="file-list">
          {files.map((file, i) => (
            <li key={`${file.name}-${i}`} className="file-list-item">
              <span className="file-list-name">{file.name}</span>
              <span className="file-list-size">{formatBytes(file.size)}</span>
              <button
                type="button"
                className="file-list-remove"
                aria-label={`Remove ${file.name}`}
                disabled={disabled}
                onClick={() => removeFile(i)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
