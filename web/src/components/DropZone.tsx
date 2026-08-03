import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { detectLanguage } from '../api/client'
import type { Language, Mode } from '../api/types'

const MAX_BYTES = 10 * 1024 * 1024
const DEFAULT_MAX_FILES = 50
const PASTE_CHAR_LIMIT = 15_000
const DETECT_DEBOUNCE_MS = 400
const SYNC_DEBOUNCE_MS = 250
/** Used when language detection fails, so a code paste still produces a
 * file with a supported extension instead of stalling forever. */
const FALLBACK_CODE_LANGUAGE: Language = 'python'

interface FileRejection {
  name: string
  reason: string
}

interface DropZoneProps {
  files: File[]
  onFilesChange: (files: File[]) => void
  disabled?: boolean
  mode?: Mode
  /** Card title, e.g. "Reference file" or "Files to check". */
  title?: string
  /** 1 makes this a single-slot zone: a new drop/paste replaces the
   * existing file instead of appending to a batch. */
  maxFiles?: number
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

export function DropZone({
  files,
  onFilesChange,
  disabled,
  mode,
  title = 'Staged files',
  maxFiles = DEFAULT_MAX_FILES,
}: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [rejections, setRejections] = useState<FileRejection[]>([])
  const [activeTab, setActiveTab] = useState<'upload' | 'paste'>('upload')
  const [pastedText, setPastedText] = useState('')
  // Auto-detection and the manual dropdown are tracked separately: a single
  // `detected` field meant the next keystroke's detection silently reverted
  // whatever the user had picked.
  const [autoDetected, setAutoDetected] = useState<Language | null>(null)
  const [override, setOverride] = useState<Language | null>(null)
  const [detecting, setDetecting] = useState(false)
  const [detectFailed, setDetectFailed] = useState(false)
  const detectSeq = useRef(0)
  // Which method populated the files currently staged here — uploading and
  // pasting can't be mixed within one zone at the same time; clear first to
  // switch. (Comparing a paste on one zone against an upload on the other
  // zone is unaffected — this only tracks origin within this instance.)
  const [origin, setOrigin] = useState<'upload' | 'paste' | null>(null)
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const single = maxFiles === 1
  const uploadBlocked = origin === 'paste' && files.length > 0
  const pasteBlocked = origin === 'upload' && files.length > 0

  const isTextMode = mode === 'text_similarity'
  //` null` means "not resolved yet" and holds the paste sync back; an
  // explicit pick always wins over auto-detection.
  const language: Language | null = isTextMode ? 'text' : (override ?? autoDetected)
  const supportedExtensions = isTextMode ? TEXT_EXTENSIONS : CODE_EXTENSIONS
  const extensionsDisplay = supportedExtensions.join(' · ')
  const hint = single ? `${extensionsDisplay} — 10 MB max` : `${extensionsDisplay} — 10 MB max, ${maxFiles} files`

  // Mirrors of props/state read from inside the paste-sync effect below
  // without becoming reactive dependencies of it — both change identity on
  // every parent/self re-render (an inline prop function, a plain-state
  // toggle), and depending on them directly would retrigger the effect
  // right after it calls onFilesChange, forming a render loop.
  const originRef = useRef(origin)
  originRef.current = origin
  const onFilesChangeRef = useRef(onFilesChange)
  onFilesChangeRef.current = onFilesChange

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
        if (count >= maxFiles) {
          newRejections.push({
            name: file.name,
            reason: single ? 'Only one reference file is allowed' : `Batch limit of ${maxFiles} files reached`,
          })
          continue
        }
        accepted.push(file)
        count += 1
      }

      return { accepted, rejections: newRejections }
    },
    [supportedExtensions, maxFiles, single],
  )

  const addFiles = useCallback(
    (incoming: FileList | File[]) => {
      const incomingArr = Array.from(incoming)
      if (files.length > 0 && origin !== null && origin !== 'upload') {
        setRejections(
          incomingArr.map((f) => ({
            name: f.name,
            reason: 'Clear pasted content first to switch to upload',
          })),
        )
        return
      }

      if (single) {
        // A single-slot zone: the newest valid file replaces whatever was there.
        const { accepted, rejections: newRejections } = validate(incomingArr.slice(0, 1), 0)
        if (accepted.length > 0) {
          onFilesChange(accepted)
          setOrigin('upload')
        }
        setRejections(newRejections)
        return
      }
      const { accepted, rejections: newRejections } = validate(incomingArr, files.length)
      if (accepted.length > 0) {
        onFilesChange([...files, ...accepted])
        setOrigin('upload')
      }
      setRejections(newRejections)
    },
    [files, onFilesChange, validate, single, origin],
  )

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    if (disabled || uploadBlocked) return
    addFiles(e.dataTransfer.files)
  }

  const resetPasteState = () => {
    setPastedText('')
    setAutoDetected(null)
    setOverride(null)
    setDetectFailed(false)
  }

  const clearFiles = () => {
    onFilesChange([])
    setOrigin(null)
    resetPasteState()
  }

  const removeFile = (index: number) => {
    const next = [...files]
    next.splice(index, 1)
    onFilesChange(next)
    if (next.length === 0) {
      setOrigin(null)
      if (origin === 'paste') resetPasteState()
    }
  }

  const handlePasteChange = (text: string) => {
    setPastedText(text.slice(0, PASTE_CHAR_LIMIT))
  }

  // The parent can clear `files` out from under this zone (switching
  // mode, "New scan") without going through clearFiles()/removeFile()
  // above — without this, leftover local paste state would silently
  // resurrect itself the next time the sync effect below happens to
  // re-run (e.g. `validate`'s identity changing on a mode switch).
  useEffect(() => {
    if (files.length === 0 && (origin !== null || pastedText !== '')) {
      setOrigin(null)
      setPastedText('')
      setAutoDetected(null)
      setOverride(null)
      setDetectFailed(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files.length])

  // Auto-detect language shortly after typing stops. There is no "Add"
  // step, so detection has to resolve on its own — waiting for blur would
  // leave it pending at the moment the user clicks Run Scan. The sequence
  // ref discards a slow earlier response that lands after a newer one:
  // clearing the debounce timer doesn't cancel a request already in flight.
  useEffect(() => {
    if (isTextMode || !pastedText.trim()) return
    const id = window.setTimeout(() => {
      const seq = ++detectSeq.current
      setDetecting(true)
      detectLanguage(pastedText)
        .then((res) => {
          if (seq !== detectSeq.current) return
          setAutoDetected(res.language)
          setDetectFailed(false)
        })
        .catch(() => {
          if (seq !== detectSeq.current) return
          // Don't strand the paste: fall back to a supported code extension
          // and tell the user to pick one if it guessed wrong. Leaving this
          // null would block the sync effect below forever.
          setAutoDetected(FALLBACK_CODE_LANGUAGE)
          setDetectFailed(true)
        })
        .finally(() => {
          if (seq === detectSeq.current) setDetecting(false)
        })
    }, DETECT_DEBOUNCE_MS)
    return () => window.clearTimeout(id)
  }, [pastedText, isTextMode])

  // Keeps whatever is currently in the paste field synced into `files` as a
  // single live entry — no "Add" click required. Debounced: this allocates a
  // File and calls up into the parent, so running it per keystroke would
  // re-render the whole app on every character.
  useEffect(() => {
    const trimmed = pastedText.trim()

    if (!trimmed) {
      if (originRef.current === 'paste') {
        onFilesChangeRef.current([])
        setOrigin(null)
      }
      setRejections([])
      return
    }

    if (originRef.current === 'upload') return

    // Hold off while the debounced detection above is still pending, so a
    // code paste isn't briefly rejected as the wrong extension.
    if (!isTextMode && language === null) {
      setRejections([])
      return
    }

    const id = window.setTimeout(() => {
      const ext = LANGUAGE_EXTENSION[language ?? 'text']
      const file = new File([pastedText], `pasted${ext}`, { type: 'text/plain' })

      const { accepted, rejections: newRejections } = validate([file], 0)
      setRejections(newRejections)

      if (accepted.length === 0) {
        if (originRef.current === 'paste') onFilesChangeRef.current([])
        return
      }

      onFilesChangeRef.current([file])
      if (originRef.current !== 'paste') setOrigin('paste')
    }, SYNC_DEBOUNCE_MS)
    return () => window.clearTimeout(id)
  }, [pastedText, language, isTextMode, validate])

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">
          {title} ({files.length}{single ? '/1' : ''})
        </span>
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
            <button type="button" className="tab-btn dropzone-clear" onClick={clearFiles} disabled={disabled}>
              Clear
            </button>
          )}
        </div>
      </div>

      {activeTab === 'upload' ? (
        <div
          className={`dropzone${isDragging ? ' dropzone-active' : ''}${
            disabled || uploadBlocked ? ' dropzone-disabled' : ''
          }`}
          onDragOver={(e) => {
            e.preventDefault()
            if (!disabled && !uploadBlocked) setIsDragging(true)
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
        >
          <label htmlFor={inputId} className="dropzone-label">
            <span className="dropzone-plus" aria-hidden="true">
              +
            </span>
            <span className="dropzone-hint">
              {uploadBlocked ? (
                <>
                  Clear pasted content first…{' '}
                  <em>Upload and paste can't be mixed in the same zone</em>
                </>
              ) : (
                <>
                  {single ? 'Add reference file… ' : 'Add files… '}
                  <em>{hint}</em>
                </>
              )}
            </span>
          </label>
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            multiple={!single}
            accept={supportedExtensions.join(',')}
            disabled={disabled || uploadBlocked}
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files)
              e.target.value = ''
            }}
          />
        </div>
      ) : (
        <div className="paste-area">
          {pasteBlocked && (
            <p className="dropzone-blocked-note">
              Clear uploaded files first — upload and paste can't be mixed in the same zone.
            </p>
          )}
          <textarea
            value={pastedText}
            onChange={(e) => handlePasteChange(e.target.value)}
            onBlur={handlePasteBlur}
            disabled={disabled || pasteBlocked}
            placeholder={
              isTextMode
                ? 'Paste your text here — it scans directly, no need to add it (up to 15,000 characters)…'
                : 'Paste your code here — it scans directly, no need to add it (up to 15,000 characters)…'
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
                      : pastedText.trim()
                        ? ' · waiting to detect language…'
                        : ''}
                </span>
              )}
            </span>
            {!isTextMode && (
              <select
                aria-label="Override detected language"
                value={detected ?? ''}
                disabled={disabled || pasteBlocked || !pastedText.trim()}
                onChange={(e) => setDetected((e.target.value || null) as Language | null)}
              >
                <option value="">Auto-detect</option>
                <option value="python">Python</option>
                <option value="java">Java</option>
                <option value="c">C</option>
                <option value="cpp">C++</option>
              </select>
            )}
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
