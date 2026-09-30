import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import type { Mode } from '../../api/types'
import { panelMotion, spring } from '../../lib/motion'
import { UploadIcon } from '../icons'
import { FileList } from './FileList'
import { PasteBox } from './PasteBox'
import { MAX_FILES, MODE_EXTENSIONS, validateFiles } from './rules'
import type { FileRejection } from './rules'

type Tab = 'upload' | 'paste'

interface DropZoneProps {
  label: string
  description?: string
  files: File[]
  onFilesChange: (files: File[]) => void
  mode: Mode
  /** 1 makes a single slot: a new file replaces the current one. */
  maxFiles?: number
  disabled?: boolean
}

export function DropZone({
  label,
  description,
  files,
  onFilesChange,
  mode,
  maxFiles = MAX_FILES,
  disabled,
}: DropZoneProps) {
  const [tab, setTab] = useState<Tab>('upload')
  const [dragging, setDragging] = useState(false)
  const [rejections, setRejections] = useState<FileRejection[]>([])
  const [pasteKey, setPasteKey] = useState(0)
  const dragDepth = useRef(0)
  const pasteFile = useRef<File | null>(null)
  const uid = useId()
  const single = maxFiles === 1
  const extensions = MODE_EXTENSIONS[mode]

  // The parent can drop files out from under this zone (mode switch, new
  // scan, a single-slot upload replacing a paste). When the pasted file is
  // gone, reset the paste box so its text can't resurrect it.
  useEffect(() => {
    if (pasteFile.current && !files.includes(pasteFile.current)) {
      pasteFile.current = null
      setPasteKey((k) => k + 1)
    }
  }, [files])

  const addFiles = (incoming: FileList | File[]) => {
    const candidates = Array.from(incoming)
    if (single) {
      const { accepted, rejections: rejected } = validateFiles(candidates.slice(0, 1), {
        mode,
        existingCount: 0,
        maxFiles: 1,
      })
      setRejections(rejected)
      if (accepted.length) onFilesChange(accepted)
      return
    }
    const { accepted, rejections: rejected } = validateFiles(candidates, {
      mode,
      existingCount: files.length,
      maxFiles,
    })
    setRejections(rejected)
    if (accepted.length) onFilesChange([...files, ...accepted])
  }

  /** Keep the paste box's live file in the list: replaced in place while
   * typing, removed when cleared. */
  const handlePaste = (next: File | null) => {
    const previous = pasteFile.current
    if (!next && !previous) return
    if (next && !previous && !single && files.length >= maxFiles) {
      setRejections([{ name: next.name, reason: `The ${maxFiles}-file limit is reached` }])
      return
    }
    pasteFile.current = next
    setRejections([])
    if (single) {
      onFilesChange(next ? [next] : [])
      return
    }
    const hadPrevious = previous !== null && files.includes(previous)
    const replaced = hadPrevious ? files.map((f) => (f === previous ? next : f)) : [...files, next]
    onFilesChange(replaced.filter((f): f is File => f !== null))
  }

  const removeFile = (file: File) => {
    onFilesChange(files.filter((f) => f !== file))
    setRejections([])
  }

  const clearAll = () => {
    onFilesChange([])
    setRejections([])
  }

  const dragHandlers = {
    onDragEnter: (e: DragEvent) => {
      e.preventDefault()
      if (disabled) return
      dragDepth.current += 1
      setDragging(true)
    },
    onDragOver: (e: DragEvent) => e.preventDefault(),
    onDragLeave: () => {
      dragDepth.current = Math.max(0, dragDepth.current - 1)
      if (dragDepth.current === 0) setDragging(false)
    },
    onDrop: (e: DragEvent) => {
      e.preventDefault()
      dragDepth.current = 0
      setDragging(false)
      if (disabled) return
      setTab('upload')
      addFiles(e.dataTransfer.files)
    },
  }

  return (
    <section className="zone" aria-labelledby={`${uid}-label`} data-dragging={dragging || undefined} {...dragHandlers}>
      <div className="zone-head">
        <div className="zone-heading">
          <h3 id={`${uid}-label`} className="zone-title">
            {label}
            <span className="zone-count num">
              {files.length}
              {single ? '/1' : ''}
            </span>
          </h3>
          {description && <p className="zone-description">{description}</p>}
        </div>
        <div className="mini-tabs" role="tablist" aria-label={`${label}: input method`}>
          {(['upload', 'paste'] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              id={`${uid}-${value}-tab`}
              aria-selected={tab === value}
              aria-controls={`${uid}-panel`}
              className="mini-tab"
              disabled={disabled}
              onClick={() => setTab(value)}
            >
              {tab === value && (
                <motion.span layoutId={`${uid}-tab`} className="mini-tab-thumb" transition={spring.snappy} />
              )}
              <span className="mini-tab-label">{value === 'upload' ? 'Upload' : 'Paste'}</span>
            </button>
          ))}
        </div>
      </div>

      <div role="tabpanel" id={`${uid}-panel`} aria-labelledby={`${uid}-${tab}-tab`}>
        {tab === 'upload' ? (
          <label className="dropzone" data-disabled={disabled || undefined}>
            <motion.span
              className="dropzone-icon"
              animate={dragging ? { y: -3, scale: 1.08 } : { y: 0, scale: 1 }}
              transition={spring.snappy}
            >
              <UploadIcon size={18} />
            </motion.span>
            <span className="dropzone-text">
              <span className="dropzone-primary">
                {dragging ? 'Drop to add' : single ? 'Choose a file or drop it here' : 'Choose files or drop them here'}
              </span>
              <span className="dropzone-secondary">
                {extensions.join(' · ')} · up to 10 MB{single ? '' : ` · ${maxFiles} files`}
              </span>
            </span>
            <input
              className="visually-hidden"
              type="file"
              multiple={!single}
              accept={extensions.join(',')}
              disabled={disabled}
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </label>
        ) : (
          <PasteBox key={`${mode}-${pasteKey}`} mode={mode} disabled={disabled} onChange={handlePaste} />
        )}
      </div>

      <AnimatePresence initial={false}>
        {rejections.length > 0 && (
          <motion.ul className="notice notice-danger rejections" role="alert" {...panelMotion}>
            {rejections.map((r, i) => (
              <li key={`${r.name}-${i}`}>
                <strong className="truncate" title={r.name}>
                  {r.name}
                </strong>
                <span>{r.reason}</span>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>

      {files.length > 0 && (
        <>
          <FileList files={files} onRemove={removeFile} disabled={disabled} />
          {files.length > 1 && (
            <button type="button" className="btn btn-link zone-clear" onClick={clearAll} disabled={disabled}>
              Remove all
            </button>
          )}
        </>
      )}
    </section>
  )
}
