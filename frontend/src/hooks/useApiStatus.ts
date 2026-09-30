import { useCallback, useEffect, useRef, useState } from 'react'
import { getStatus } from '../api/client'
import type { StorageBackend } from '../api/types'

const POLL_MS = 15_000

export type ApiStatus =
  | { state: 'checking' }
  | { state: 'online'; storage?: StorageBackend; version: string }
  | { state: 'offline' }

/** Polls `/api/status` so the header can say whether scans will work, and
 * where their results are stored. `retry` re-checks immediately. */
export function useApiStatus(): { status: ApiStatus; retry: () => void } {
  const [status, setStatus] = useState<ApiStatus>({ state: 'checking' })
  const seq = useRef(0)

  const check = useCallback(() => {
    const mine = ++seq.current
    getStatus()
      .then((res) => {
        if (mine === seq.current) {
          setStatus({ state: 'online', storage: res.storage, version: res.version })
        }
      })
      .catch(() => {
        if (mine === seq.current) setStatus({ state: 'offline' })
      })
  }, [])

  useEffect(() => {
    check()
    const id = window.setInterval(check, POLL_MS)
    return () => window.clearInterval(id)
  }, [check])

  const retry = useCallback(() => {
    setStatus({ state: 'checking' })
    check()
  }, [check])

  return { status, retry }
}
