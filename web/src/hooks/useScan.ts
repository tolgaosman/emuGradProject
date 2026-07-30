import { useCallback, useRef, useState } from 'react'
import { runCheck } from '../api/client'
import type { CheckResponse } from '../api/types'
import type { CheckOptions } from '../api/client'
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

  const start = useCallback((options: StartOptions) => {
    const myGeneration = ++generation.current
    setState({ status: 'uploading', progress: 0 })

    runCheck({
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
      .then((result) => {
        if (myGeneration !== generation.current) return
        setState({ status: 'ready', result })
      })
      .catch((err: unknown) => {
        if (myGeneration !== generation.current) return
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
    setState({ status: 'idle' })
  }, [])

  return { state, start, reset }
}
