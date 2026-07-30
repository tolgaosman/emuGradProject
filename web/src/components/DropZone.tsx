import { useCallback, useId, useRef, useState } from 'react'
import type { DragEvent } from 'react'

const SUPPORTED_EXTENSIONS = ['.txt', '.py', '.pdf', '.docx']
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

function validate(candidate: File[], existingCount: number): { accepted: File[]; rejections: FileRejection[] } {
  const accepted: File[] = []
  const rejections: FileRejection[] = []
  let count = existingCount

  for (const file of candidate) {
    if (!SUPPORTED_EXTENSIONS.includes(extensionOf(file.name))) {
      rejections.push({ name: file.name, reason: 'Unsupported format' })
      continue
    }
    if (file.size === 0) {
      rejections.push({ name: file.name, reason: 'File is empty' })
      continue
    }
    if (file.size > MAX_BYTES) {
      rejections.push({ name: file.name, reason: 'Exceeds 10 MB limit' })
      continue
    }
    if (count >= MAX_FILES) {
      rejections.push({ name: file.name, reason: `Batch limit of ${MAX_FILES} files reached` })
      continue
    }
    accepted.push(file)
    count += 1
  }

  return { accepted, rejections }
}

export function DropZone({ files, onFilesChange, disabled }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [rejections, setRejections] = useState<FileRejection[]>([])
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)

  const addFiles = useCallback(
    (incoming: FileList | File[]) => {
      const { accepted, rejections: newRejections } = validate(Array.from(incoming), files.length)
      if (accepted.length > 0) onFilesChange([...files, ...accepted])
      setRejections(newRejections)
    },
    [files, onFilesChange],
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

  return (
    <div className="dropzone-wrap">
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
            .txt · .py · .pdf · .docx — up to 10 MB each, {MAX_FILES} files max
          </p>
          <span className="btn btn-secondary dropzone-browse">Browse files</span>
        </label>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          multiple
          accept={SUPPORTED_EXTENSIONS.join(',')}
          disabled={disabled}
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      {rejections.length > 0 && (
        <ul className="dropzone-rejections" role="alert">
          {rejections.map((r) => (
            <li key={r.name}>
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
