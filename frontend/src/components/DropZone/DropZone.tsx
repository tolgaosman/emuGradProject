import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import type { Mode } from '../../api/types'
import { formatBytes } from '../../lib/format'
import { panelMotion, spring } from '../../lib/motion'
import { UploadIcon } from '../icons'
import { FileList } from './FileList'
import { PasteBox } from './PasteBox'
import { MAX_FILES, MODE_EXTENSIONS, validateFiles } from './rules'
import type { FileRejection } from './rules'

type Tab = 'upload' | 'paste'

interface DropZoneProps {
  label: string
  files: File[]
  onFilesChange: (files: File[]) => void
  mode: Mode
  maxFiles?: number
  disabled?: boolean
}

async function readDroppedItems(dataTransfer: DataTransfer): Promise<File[]> {
  const items = Array.from(dataTransfer.items ?? [])
  const entries = items
    .map((item) => item.webkitGetAsEntry?.())
    .filter((entry): entry is FileSystemEntry => entry !== null && entry !== undefined)

  if (entries.length === 0 || !entries.some((e) => e.isDirectory)) {
    return Array.from(dataTransfer.files)
  }

  const collected: File[] = []
  const visit = (entry: FileSystemEntry): Promise<void> =>
    new Promise((resolve) => {
      if (entry.isFile) {
        ;(entry as FileSystemFileEntry).file(
          (f) => {
            if (!f.name.startsWith('.')) collected.push(f)
            resolve()
          },
          () => resolve(),
        )
      } else if (entry.isDirectory) {
        const reader = (entry as FileSystemDirectoryEntry).createReader()
        const readBatch = () => {
          reader.readEntries(
            async (batch) => {
              if (batch.length === 0) {
                resolve()
                return
              }
              await Promise.all(batch.map(visit))
              readBatch()
            },
            () => resolve(),
          )
        }
        readBatch()
      } else {
        resolve()
      }
    })

  await Promise.all(entries.map(visit))
  return collected.length > 0 ? collected : Array.from(dataTransfer.files)
}

export function DropZone({
  label,
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
  const acceptAttr = single ? extensions.join(',') : [...extensions, '.zip'].join(',')
  const totalBytes = files.reduce((sum, f) => sum + f.size, 0)

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

  const handlePaste = (next: File | null) => {
    const previous = pasteFile.current
    if (!next && !previous) return
    if (next && !previous && !single && files.length >= maxFiles) {
      setRejections([{ name: next.name, reason: `Max ${maxFiles} files` }])
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
      void readDroppedItems(e.dataTransfer).then(addFiles)
    },
  }

  return (
    <section className="zone" aria-labelledby={`${uid}-label`} data-dragging={dragging || undefined} {...dragHandlers}>
      <div className="zone-head">
        <h3 id={`${uid}-label`} className="zone-title">
          {label}
          <span className="zone-count num">
            {files.length}
            {single ? '/1' : ''}
          </span>
        </h3>
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
              <span className="mini-tab-label">{value === 'upload' ? 'Files' : 'Paste'}</span>
            </button>
          ))}
        </div>
      </div>

      <div role="tabpanel" id={`${uid}-panel`} aria-labelledby={`${uid}-${tab}-tab`}>
        {tab === 'upload' ? (
          <label className="dropzone" data-disabled={disabled || undefined}>
            <motion.span
              className="dropzone-icon"
              animate={dragging ? { y: -2, scale: 1.06 } : { y: 0, scale: 1 }}
              transition={spring.snappy}
            >
              <UploadIcon size={16} />
            </motion.span>
            <span className="dropzone-text">
              <span className="dropzone-primary">
                {dragging ? 'Drop here' : single ? 'Drop file or browse' : 'Drop files, folder, or .zip'}
              </span>
              <span className="dropzone-secondary">
                {extensions.join(' ')}
                {single ? '' : ' .zip'}
              </span>
            </span>
            <input
              className="visually-hidden"
              type="file"
              multiple={!single}
              accept={acceptAttr}
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
            <div className="zone-foot">
              <span className="zone-foot-meta num">{formatBytes(totalBytes)}</span>
              <button type="button" className="btn btn-link zone-clear" onClick={clearAll} disabled={disabled}>
                Clear
              </button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
