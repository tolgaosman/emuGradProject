import { createContext, useContext } from 'react'

export type Tone = 'success' | 'error'

export interface ToastApi {
  show: (message: string, tone?: Tone) => void
}

export const ToastContext = createContext<ToastApi | null>(null)

export function useToast(): ToastApi {
  const api = useContext(ToastContext)
  if (!api) throw new Error('useToast must be used inside <ToastProvider>')
  return api
}
