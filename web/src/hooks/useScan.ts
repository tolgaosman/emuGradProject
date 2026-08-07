import { useCallback, useEffect, useRef, useState } from 'react'
import { AbortedError, runCheck } from '../api/client'
import type { CheckResponse } from '../api/types'
import type { CheckOptions, RunningCheck } from '../api/client'
import { ApiError } from '../api/types'

export type ScanState =
  | { status: 'idle' }
  | { status: 'uploading'; progress: number }
  | { status: 'processing' }
  | { status: 'ready'; result: CheckResponse }
  | { status: 'error'; message: string; code?: string }

export type StartOptions = Omit<CheckOptions, 'onProgress'>

export function useScan() {
  const [state, setState] = useState<ScanState>({ status: 'idle' })
  const generation = useRef(0)
  const inFlight = useRef<RunningCheck | null>(null)

  const start = useCallback((options: StartOptions) => {
    // Cancel any earlier scan outright rather than just ignoring its
    // result — otherwise a superseded upload keeps running to completion and
    // the backend keeps scanning files nobody is waiting for.
    inFlight.current?.abort()

    const myGeneration = ++generation.current
    setState({ status: 'uploading', progress: 0 })

    const running = runCheck({
      ...options,
      onProgress: (fraction) => {
        if (myGeneration !== generation.current) return
        if (fraction >= 1) {
          setState({ status: 'processing' })
        } else {
          setState({ status: 'uploading', progress: fraction })
        }
      },
    })
    inFlight.current = running

    running.promise
      .then((result) => {
        if (myGeneration !== generation.current) return
        inFlight.current = null
        setState({ status: 'ready', result })
      })
      .catch((err: unknown) => {
        if (myGeneration !== generation.current) return
        inFlight.current = null
        // A cancel is a deliberate act by newer state, never an error to
        // surface — the newer scan or the reset already set the UI.
        if (err instanceof AbortedError) return
        if (err instanceof ApiError) {
          setState({ status: 'error', message: err.message, code: err.code })
        } else {
          setState({
            status: 'error',
            message: err instanceof Error ? err.message : 'Something went wrong.',
          })
        }
      })
  }, [])

  const reset = useCallback(() => {
    generation.current += 1
    inFlight.current?.abort()
    inFlight.current = null
    setState({ status: 'idle' })
  }, [])

  // Don't leave an upload running after the component goes away.
  useEffect(() => () => inFlight.current?.abort(), [])

  return { state, start, reset }
}
