import { useCallback, useId, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { detectLanguage } from '../api/client'
import type { Language, Mode } from '../api/types'

const MAX_BYTES = 10 * 1024 * 1024
const MAX_FILES = 50
const PASTE_CHAR_LIMIT = 15_000

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

const TEXT_EXTENSIONS = ['.txt', '.pdf', '.docx']
const CODE_EXTENSIONS = ['.py', '.java', '.c', '.h', '.cpp', '.cc', '.hpp']

const LANGUAGE_EXTENSION: Record<Language, string> = {
  python: '.py',
  java: '.java',
  c: '.c',
  cpp: '.cpp',
  text: '.txt',
}

const LANGUAGE_LABEL: Record<Language, string> = {
  python: 'Python',
  java: 'Java',
  c: 'C',
  cpp: 'C++',
  text: 'Text',
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
  const [detected, setDetected] = useState<Language | null>(null)
  const [detecting, setDetecting] = useState(false)
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)

  const isTextMode = mode === 'ai_text' || mode === 'text_similarity'
  const supportedExtensions = isTextMode ? TEXT_EXTENSIONS : CODE_EXTENSIONS
  const extensionsDisplay = supportedExtensions.join(' · ')

  const validate = useCallback(
    (candidate: File[], existingCount: number): { accepted: File[]; rejections: FileRejection[] } => {
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
    },
    [supportedExtensions],
  )

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

  const runDetection = useCallback(
    (text: string) => {
      if (isTextMode || !text.trim()) {
        setDetected(null)
        return
      }
      setDetecting(true)
      detectLanguage(text)
        .then((res) => setDetected(res.language))
        .catch(() => setDetected(null))
        .finally(() => setDetecting(false))
    },
    [isTextMode],
  )

  const handlePasteChange = (text: string) => {
    setPastedText(text.slice(0, PASTE_CHAR_LIMIT))
  }

  const handlePasteBlur = () => {
    runDetection(pastedText)
  }

  const handlePasteSubmit = () => {
    if (!pastedText.trim()) return
    const language: Language = isTextMode ? 'text' : (detected ?? 'text')
    const ext = LANGUAGE_EXTENSION[language]
    const file = new File([pastedText], `pasted_${files.length + 1}${ext}`, { type: 'text/plain' })
    addFiles([file])
    setPastedText('')
    setDetected(null)
    setActiveTab('upload')
  }

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Staged files ({files.length})</span>
        <div className="dropzone-tabs">
          <button
            type="button"
            className={`tab-btn${activeTab === 'upload' ? ' tab-btn-active' : ''}`}
            onClick={() => setActiveTab('upload')}
            disabled={disabled}
          >
            Upload
          </button>
          <button
            type="button"
            className={`tab-btn${activeTab === 'paste' ? ' tab-btn-active' : ''}`}
            onClick={() => setActiveTab('paste')}
            disabled={disabled}
          >
            Paste
          </button>
          {files.length > 0 && (
            <button
              type="button"
              className="tab-btn dropzone-clear"
              onClick={() => onFilesChange([])}
              disabled={disabled}
            >
              Clear
            </button>
          )}
        </div>
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
            <span className="dropzone-plus" aria-hidden="true">
              +
            </span>
            <span className="dropzone-hint">
              Add files… <em>{extensionsDisplay} — 10 MB max, {MAX_FILES} files</em>
            </span>
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
            onChange={(e) => handlePasteChange(e.target.value)}
            onBlur={handlePasteBlur}
            disabled={disabled}
            placeholder={
              isTextMode
                ? 'Paste your text here (up to 15,000 characters)…'
                : 'Paste your code here (up to 15,000 characters)…'
            }
            maxLength={PASTE_CHAR_LIMIT}
          />
          <div className="paste-area-footer">
            <span className="paste-area-count">
              {pastedText.length} / {PASTE_CHAR_LIMIT.toLocaleString()} characters
              {!isTextMode && (
                <span className="paste-area-language">
                  {detecting
                    ? ' · detecting…'
                    : detected
                      ? ` · detected ${LANGUAGE_LABEL[detected]}`
                      : ''}
                </span>
              )}
            </span>
            {!isTextMode && (
              <select
                aria-label="Override detected language"
                value={detected ?? ''}
                disabled={disabled || !pastedText.trim()}
                onChange={(e) => setDetected((e.target.value || null) as Language | null)}
              >
                <option value="">Auto-detect</option>
                <option value="python">Python</option>
                <option value="java">Java</option>
                <option value="c">C</option>
                <option value="cpp">C++</option>
              </select>
            )}
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handlePasteSubmit}
              disabled={disabled || !pastedText.trim()}
            >
              Add
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
