import { AnimatePresence, motion } from 'motion/react'
import { formatBytes } from '../../lib/format'
import { spring } from '../../lib/motion'
import { CloseIcon } from '../icons'
import { formatBadge } from './rules'

/** Stable per-File identity for React keys: two picks of the same file are
 * distinct `File` objects, and index keys would mis-animate on removal. */
const fileIds = new WeakMap<File, string>()
let nextFileId = 0
function fileKey(file: File): string {
  let id = fileIds.get(file)
  if (!id) {
    id = `f${(nextFileId += 1)}`
    fileIds.set(file, id)
  }
  return id
}

interface FileListProps {
  files: readonly File[]
  onRemove: (file: File) => void
  disabled?: boolean
}

export function FileList({ files, onRemove, disabled }: FileListProps) {
  return (
    <ul className="file-list" aria-label="Staged files">
      <AnimatePresence initial={false}>
        {files.map((file) => (
          <motion.li
            key={fileKey(file)}
            layout="position"
            className="file-row"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: 8, transition: { duration: 0.14 } }}
            transition={spring.snappy}
          >
            <span className="file-badge" aria-hidden="true">
              {formatBadge(file.name)}
            </span>
            <span className="file-name truncate" title={file.name}>
              {file.name}
            </span>
            <span className="file-size num">{formatBytes(file.size)}</span>
            <button
              type="button"
              className="icon-btn icon-btn-sm"
              aria-label={`Remove ${file.name}`}
              disabled={disabled}
              onClick={() => onRemove(file)}
            >
              <CloseIcon size={14} />
            </button>
          </motion.li>
        ))}
      </AnimatePresence>
    </ul>
  )
}
