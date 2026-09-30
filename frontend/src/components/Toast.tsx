import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ToastContext } from '../hooks/useToast'
import type { Tone } from '../hooks/useToast'
import { spring } from '../lib/motion'
import { AlertIcon, CheckIcon } from './icons'

interface Toast {
  id: number
  tone: Tone
  message: string
}

const DISMISS_MS = 4200

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(0)

  const show = useCallback((message: string, tone: Tone = 'success') => {
    const id = (nextId.current += 1)
    setToasts((current) => [...current.slice(-2), { id, tone, message }])
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), DISMISS_MS)
  }, [])

  const api = useMemo(() => ({ show }), [show])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        <AnimatePresence initial={false}>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              layout
              className="toast"
              data-tone={toast.tone}
              initial={{ opacity: 0, y: 12, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96, transition: { duration: 0.15 } }}
              transition={spring.snappy}
            >
              {toast.tone === 'error' ? <AlertIcon /> : <CheckIcon />}
              {toast.message}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}
