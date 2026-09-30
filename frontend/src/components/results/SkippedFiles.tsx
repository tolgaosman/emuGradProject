import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import type { FileError } from '../../api/types'
import { pluralize } from '../../lib/format'
import { EASE_OUT } from '../../lib/motion'
import { AlertIcon, ChevronIcon } from '../icons'

/** Files the server couldn't use, collapsed to one line by default so a
 * partial scan still leads with its results. */
export function SkippedFiles({ errors }: { errors: FileError[] }) {
  const [open, setOpen] = useState(false)
  if (errors.length === 0) return null

  return (
    <div className="notice notice-warning">
      <button type="button" className="notice-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <AlertIcon />
        <span>{pluralize(errors.length, 'file was', 'files were')} skipped</span>
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2, ease: EASE_OUT }}>
          <ChevronIcon size={14} />
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.ul
            className="notice-list"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: EASE_OUT }}
          >
            {errors.map((e, i) => (
              <li key={`${e.file}-${i}`}>
                <strong className="truncate" title={e.file}>
                  {e.file}
                </strong>
                <span>{e.error}</span>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  )
}
