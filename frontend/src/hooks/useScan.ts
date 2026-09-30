import { useCallback, useEffect, useRef, useState } from 'react'
import { AbortedError, NetworkError, getReport, runCheck } from '../api/client'
import type { CheckOptions, RunningCheck } from '../api/client'
import type { CheckResponse, FileError } from '../api/types'
import { ApiError } from '../api/types'
import type { Workspace } from '../lib/deriveResults'

/** Where a result came from and how to lay it out. A reopened scan has no
 * record of which file was the reference, so it is shown as a batch. */
export interface ScanMeta {
  layout: Workspace
  referenceName?: string
  source: 'scan' | 'history'
}

export type ScanState =
  | { status: 'idle' }
  | { status: 'uploading'; progress: number; meta: ScanMeta }
  | { status: 'processing'; meta: ScanMeta }
  | { status: 'loading'; meta: ScanMeta }
  | { status: 'ready'; result: CheckResponse; meta: ScanMeta }
  | { status: 'error'; message: string; code?: string; fileErrors?: FileError[]; meta: ScanMeta }

export type StartOptions = Omit<CheckOptions, 'onProgress'>

function toErrorState(err: unknown, meta: ScanMeta): ScanState {
  if (err instanceof ApiError) {
    return {
      status: 'error',
      message: err.message,
      code: err.code,
      fileErrors: err.body.file_errors,
      meta,
    }
  }
  return {
    status: 'error',
    message: err instanceof Error ? err.message : 'Something went wrong.',
    code: err instanceof NetworkError ? 'network' : undefined,
    meta,
  }
}

export function useScan() {
  const [state, setState] = useState<ScanState>({ status: 'idle' })
  const generation = useRef(0)
  const inFlight = useRef<RunningCheck | null>(null)

  /** Cancel whatever is running and claim a new generation; results from an
   * older generation are dropped when they land. */
  const supersede = useCallback(() => {
    inFlight.current?.abort()
    inFlight.current = null
    generation.current += 1
    return generation.current
  }, [])

  const start = useCallback(
    (options: StartOptions, meta: Omit<ScanMeta, 'source'>) => {
      const mine = supersede()
      const scanMeta: ScanMeta = { ...meta, source: 'scan' }
      setState({ status: 'uploading', progress: 0, meta: scanMeta })

      const running = runCheck({
        ...options,
        onProgress: (fraction) => {
          if (mine !== generation.current) return
          setState(
            fraction >= 1
              ? { status: 'processing', meta: scanMeta }
              : { status: 'uploading', progress: fraction, meta: scanMeta },
          )
        },
      })
      inFlight.current = running

      running.promise
        .then((result) => {
          if (mine !== generation.current) return
          inFlight.current = null
          setState({ status: 'ready', result, meta: scanMeta })
        })
        .catch((err: unknown) => {
          // A cancel is a deliberate act by newer state, never an error.
          if (mine !== generation.current || err instanceof AbortedError) return
          inFlight.current = null
          setState(toErrorState(err, scanMeta))
        })
    },
    [supersede],
  )

  const open = useCallback(
    (scanId: string) => {
      const mine = supersede()
      const meta: ScanMeta = { layout: 'batch', source: 'history' }
      setState({ status: 'loading', meta })
      getReport(scanId)
        .then((result) => {
          if (mine === generation.current) setState({ status: 'ready', result, meta })
        })
        .catch((err: unknown) => {
          if (mine === generation.current) setState(toErrorState(err, meta))
        })
    },
    [supersede],
  )

  const reset = useCallback(() => {
    supersede()
    setState({ status: 'idle' })
  }, [supersede])

  // Don't leave an upload running after the component goes away.
  useEffect(() => () => inFlight.current?.abort(), [])

  return { state, start, open, reset }
}
