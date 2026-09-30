import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { EASE_OUT } from '../../lib/motion'
import { ChevronIcon, DownloadIcon } from '../icons'

export type ExportKind = 'html' | 'csv' | 'heatmap'

const ITEMS: readonly { kind: ExportKind; label: string; detail: string }[] = [
  { kind: 'html', label: 'Full report', detail: 'HTML · highlighted pairs' },
  { kind: 'csv', label: 'Similarity matrix', detail: 'CSV · every score' },
  { kind: 'heatmap', label: 'Heatmap', detail: 'PNG · 300 DPI' },
]

interface ExportMenuProps {
  onExport: (kind: ExportKind) => void
  busy: ExportKind | null
}

export function ExportMenu({ onExport, busy }: ExportMenuProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([])
  const menuId = useId()

  useEffect(() => {
    if (!open) return
    itemRefs.current[0]?.focus()
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  const close = () => {
    setOpen(false)
    buttonRef.current?.focus()
  }

  const handleMenuKeys = (e: KeyboardEvent) => {
    const items = itemRefs.current.filter((el): el is HTMLButtonElement => el !== null)
    const current = items.indexOf(document.activeElement as HTMLButtonElement)
    if (e.key === 'Escape') {
      e.preventDefault()
      close()
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const step = e.key === 'ArrowDown' ? 1 : -1
      items[(current + step + items.length) % items.length]?.focus()
    } else if (e.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <div className="menu-root" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="btn btn-secondary btn-sm"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        <DownloadIcon />
        Export
        <ChevronIcon size={14} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            id={menuId}
            className="menu"
            role="menu"
            aria-label="Export this scan"
            onKeyDown={handleMenuKeys}
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98, transition: { duration: 0.12 } }}
            transition={{ duration: 0.18, ease: EASE_OUT }}
          >
            {ITEMS.map((item, i) => (
              <button
                key={item.kind}
                ref={(el) => {
                  itemRefs.current[i] = el
                }}
                type="button"
                role="menuitem"
                className="menu-item"
                disabled={busy !== null}
                onClick={() => {
                  onExport(item.kind)
                  close()
                }}
              >
                <span className="menu-item-label">{item.label}</span>
                <span className="menu-item-detail">{busy === item.kind ? 'Preparing…' : item.detail}</span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
