import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { deleteScan, listScans } from '../api/client'
import type { ScanHistoryEntry } from '../api/types'
import { useFocusTrap } from '../hooks/useFocusTrap'
import { useToast } from '../hooks/useToast'
import { MODE_LABEL, formatPercent, formatRelativeTime, pluralize } from '../lib/format'
import { EASE_OUT, spring } from '../lib/motion'
import { CloseIcon, HistoryIcon, RefreshIcon, TrashIcon } from './icons'
import { RiskPill } from './results/RiskPill'

type Load =
  | { state: 'loading' }
  | { state: 'ready'; scans: ScanHistoryEntry[] }
  | { state: 'error'; message: string }

interface HistoryDrawerProps {
  currentScanId: string | null
  onOpenScan: (scanId: string) => void
  onDeleted: (scanId: string) => void
  onClose: () => void
}

function describeFiles(names: string[]): string {
  if (names.length <= 2) return names.join(', ')
  return `${names.slice(0, 2).join(', ')} +${names.length - 2}`
}

export function HistoryDrawer({ currentScanId, onOpenScan, onDeleted, onClose }: HistoryDrawerProps) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [confirming, setConfirming] = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const toast = useToast()
  useFocusTrap(panelRef, true, onClose)

  const refresh = useCallback(() => {
    setLoad({ state: 'loading' })
    listScans()
      .then((scans) => setLoad({ state: 'ready', scans }))
      .catch((err: unknown) =>
        setLoad({ state: 'error', message: err instanceof Error ? err.message : 'Could not load history.' }),
      )
  }, [])

  useEffect(refresh, [refresh])

  const remove = (scanId: string) => {
    deleteScan(scanId)
      .then(() => {
        setLoad((current) =>
          current.state === 'ready'
            ? { state: 'ready', scans: current.scans.filter((s) => s.scan_uuid !== scanId) }
            : current,
        )
        setConfirming(null)
        onDeleted(scanId)
        toast.show('Scan deleted, including its stored text.')
      })
      .catch((err: unknown) => toast.show(err instanceof Error ? err.message : 'Delete failed.', 'error'))
  }

  return (
    <div className="dialog-layer">
      <motion.div
        className="overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2, ease: EASE_OUT }}
        onClick={onClose}
      />
      <motion.aside
        ref={panelRef}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-title"
        tabIndex={-1}
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%', transition: { duration: 0.22, ease: EASE_OUT } }}
        transition={spring.drawer}
      >
        <header className="drawer-head">
          <div>
            <h2 id="history-title" className="drawer-title">
              History
            </h2>
            <p className="drawer-subtitle">Saved on this machine for 90 days.</p>
          </div>
          <button type="button" className="icon-btn" aria-label="Close history" onClick={onClose}>
            <CloseIcon />
          </button>
        </header>

        <div className="drawer-body">
          {load.state === 'loading' && (
            <ul className="history-list" aria-busy="true">
              {Array.from({ length: 5 }, (_, i) => (
                <li key={i} className="skeleton skeleton-history" />
              ))}
            </ul>
          )}

          {load.state === 'error' && (
            <div className="drawer-empty" role="alert">
              <p>{load.message}</p>
              <button type="button" className="btn btn-secondary btn-sm" onClick={refresh}>
                <RefreshIcon />
                Try again
              </button>
            </div>
          )}

          {load.state === 'ready' && load.scans.length === 0 && (
            <div className="drawer-empty">
              <HistoryIcon size={20} />
              <p>No saved scans yet. Finished scans appear here.</p>
            </div>
          )}

          {load.state === 'ready' && load.scans.length > 0 && (
            <ul className="history-list">
              <AnimatePresence initial={false}>
                {load.scans.map((scan) => (
                  <motion.li
                    key={scan.scan_uuid}
                    layout
                    className="history-item"
                    data-current={scan.scan_uuid === currentScanId || undefined}
                    exit={{ opacity: 0, x: 24, transition: { duration: 0.16 } }}
                    transition={spring.snappy}
                  >
                    <button
                      type="button"
                      className="history-open"
                      onClick={() => onOpenScan(scan.scan_uuid)}
                      aria-label={`Open scan of ${pluralize(scan.file_names.length, 'file')} from ${formatRelativeTime(scan.timestamp)}`}
                    >
                      <span className="history-row">
                        <span className="history-files truncate" title={scan.file_names.join('\n')}>
                          {describeFiles(scan.file_names)}
                        </span>
                        {scan.max_score !== null && <RiskPill score={scan.max_score} />}
                      </span>
                      <span className="history-meta">
                        {MODE_LABEL[scan.mode]} · {pluralize(scan.file_names.length, 'file')}
                        {scan.max_score !== null && (
                          <>
                            {' '}
                            · top <span className="num">{formatPercent(scan.max_score)}</span>
                          </>
                        )}
                        {' · '}
                        {formatRelativeTime(scan.timestamp)}
                      </span>
                    </button>
                    {confirming === scan.scan_uuid ? (
                      <span className="history-confirm">
                        <button type="button" className="btn btn-danger btn-xs" onClick={() => remove(scan.scan_uuid)}>
                          Delete
                        </button>
                        <button type="button" className="btn btn-ghost btn-xs" onClick={() => setConfirming(null)}>
                          Keep
                        </button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="icon-btn icon-btn-sm history-delete"
                        aria-label="Delete this scan"
                        onClick={() => setConfirming(scan.scan_uuid)}
                      >
                        <TrashIcon size={14} />
                      </button>
                    )}
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          )}
        </div>
      </motion.aside>
    </div>
  )
}
