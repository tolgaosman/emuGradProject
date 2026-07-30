import { ApiError } from './types'
import type { ApiErrorBody, Algorithm, CheckResponse, PairResponse, ReportResponse } from './types'

async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  const body = await res.json()
  if (!res.ok) throw new ApiError(body as ApiErrorBody)
  return body as T
}

export async function getAlgorithms(): Promise<Algorithm[]> {
  const res = await fetch('/api/algorithms')
  const body = await parseJsonOrThrow<{ algorithms: Algorithm[] }>(res)
  return body.algorithms
}

export interface CheckOptions {
  files: File[]
  algorithm: Algorithm
  threshold: number
  onProgress?: (fraction: number) => void
}

/** Upload files and run a scan. Uses XHR (not fetch) so upload progress can
 * be reported to the caller for the drop zone's progress bar. */
export function runCheck(opts: CheckOptions): Promise<CheckResponse> {
  const { files, algorithm, threshold, onProgress } = opts

  const form = new FormData()
  form.append('algorithm', algorithm)
  form.append('threshold', String(threshold))
  for (const file of files) form.append('files', file, file.name)

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/check')

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total)
    }

    xhr.onload = () => {
      let body: unknown
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        reject(new Error('Server returned an invalid response.'))
        return
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as CheckResponse)
      } else {
        reject(new ApiError(body as ApiErrorBody))
      }
    }

    xhr.onerror = () => reject(new Error('Network error — is the PlagCheck API running?'))
    xhr.send(form)
  })
}

export async function getReport(scanId: string): Promise<ReportResponse> {
  const res = await fetch(`/api/report/${encodeURIComponent(scanId)}`)
  return parseJsonOrThrow<ReportResponse>(res)
}

export async function getPair(scanId: string, fileA: string, fileB: string): Promise<PairResponse> {
  const res = await fetch(
    `/api/report/${encodeURIComponent(scanId)}/pair/${encodeURIComponent(fileA)}/${encodeURIComponent(fileB)}`,
  )
  return parseJsonOrThrow<PairResponse>(res)
}

export function heatmapUrl(scanId: string): string {
  return `/api/report/${encodeURIComponent(scanId)}/heatmap.png`
}
