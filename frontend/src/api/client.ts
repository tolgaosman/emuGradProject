import { ApiError } from './types'
import type {
  Algorithm,
  AlgorithmsResponse,
  ApiErrorBody,
  CheckResponse,
  DetectLanguageResponse,
  Mode,
  PairResponse,
  ReportResponse,
  ScanHistoryEntry,
  StatusResponse,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

/** The server could not be reached at all (stopped, or a network failure). */
export class NetworkError extends Error {
  constructor() {
    super('Could not reach the PlagCheck server.')
    this.name = 'NetworkError'
  }
}

function isErrorBody(body: unknown): body is ApiErrorBody {
  return typeof body === 'object' && body !== null && 'code' in body && 'error' in body
}

/** Parse a JSON response, turning the `{error, code}` envelope into `ApiError`.
 * A non-JSON body (a proxy's HTML 502, say) becomes a plain, readable error
 * instead of a `SyntaxError` leaking into the UI. */
async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  let body: unknown
  try {
    body = await res.json()
  } catch {
    throw new Error(`The server answered with an unexpected response (HTTP ${res.status}).`)
  }
  if (!res.ok) {
    throw isErrorBody(body) ? new ApiError(body) : new Error(`Request failed (HTTP ${res.status}).`)
  }
  return body as T
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new NetworkError()
  }
  return parseJsonOrThrow<T>(res)
}

const reportPath = (scanId: string) => `/api/report/${encodeURIComponent(scanId)}`

const pairPath = (kind: 'pair' | 'pair-pdf', scanId: string, fileA: string, fileB: string) =>
  `${reportPath(scanId)}/${kind}/${encodeURIComponent(fileA)}/${encodeURIComponent(fileB)}`

export const getAlgorithms = () => request<AlgorithmsResponse>('/api/algorithms')

export const getStatus = () => request<StatusResponse>('/api/status')

export const listScans = (limit = 30) =>
  request<{ scans: ScanHistoryEntry[] }>(`/api/scans?limit=${limit}`).then((r) => r.scans)

/** Guess the language of a pasted code snippet (Python/Java/C/C++). */
export const detectLanguage = (text: string) =>
  request<DetectLanguageResponse>('/api/detect-language', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })

/** Both files' text plus the matched-span offsets to highlight. The span
 * filter defaults server-side to the scan's own `min_match_words`, so the
 * highlighting always matches the score being displayed. */
export const getPair = (scanId: string, fileA: string, fileB: string) =>
  request<PairResponse>(pairPath('pair', scanId, fileA, fileB))

/** Reopen a stored scan in the same shape a fresh `/api/check` returns. */
export async function getReport(scanId: string): Promise<CheckResponse> {
  const report = await request<ReportResponse>(reportPath(scanId))
  return {
    scan_id: report.scan_id,
    mode: report.mode,
    algorithm: report.algorithm_override,
    threshold: report.threshold,
    min_match_words: report.min_match_words,
    matrix: report.matrix,
    pairs: report.pairs,
    similarity_indices: report.similarity_indices,
    source_breakdowns: report.source_breakdowns,
    errors: [],
  }
}

export async function deleteScan(scanId: string): Promise<void> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${reportPath(scanId)}`, { method: 'DELETE' })
  } catch {
    throw new NetworkError()
  }
  if (!res.ok) await parseJsonOrThrow(res)
}

export const exportUrls = {
  heatmap: (scanId: string, ref?: string) =>
    `${API_BASE}${reportPath(scanId)}/heatmap.png?ref=${encodeURIComponent(ref ?? 'all')}`,
  csv: (scanId: string) => `${API_BASE}${reportPath(scanId)}/matrix.csv`,
  html: (scanId: string) => `${API_BASE}${reportPath(scanId)}/report.html`,
  pairPdf: (scanId: string, fileA: string, fileB: string) =>
    `${API_BASE}${pairPath('pair-pdf', scanId, fileA, fileB)}`,
}

function filenameFrom(disposition: string | null): string | null {
  if (!disposition) return null
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  if (encoded) return decodeURIComponent(encoded[1])
  const plain = /filename="([^"]+)"/i.exec(disposition)
  return plain ? plain[1] : null
}

/** Fetch an export and save it. Going through `fetch` (not a bare
 * `<a download>`) means a missing or expired scan surfaces as an error the
 * UI can show, rather than silently saving a JSON error body as a file. */
export async function downloadFile(url: string, fallbackName: string): Promise<void> {
  let res: Response
  try {
    res = await fetch(url)
  } catch {
    throw new NetworkError()
  }
  if (!res.ok) await parseJsonOrThrow(res)

  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filenameFrom(res.headers.get('Content-Disposition')) ?? fallbackName
  document.body.append(link)
  link.click()
  link.remove()
  // Revoke on the next task: some browsers start the download asynchronously.
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
}

export interface CheckOptions {
  files: File[]
  mode: Mode
  threshold: number
  algorithm?: Algorithm
  minMatchWords?: number
  onProgress?: (fraction: number) => void
}

/** A scan in flight. `abort()` cancels the upload so a superseded or reset
 * scan stops consuming bandwidth and server time instead of merely having
 * its result ignored. */
export interface RunningCheck {
  promise: Promise<CheckResponse>
  abort: () => void
}

/** Raised when a scan is cancelled via `RunningCheck.abort()`; callers use
 * this to tell a deliberate cancel apart from a real failure. */
export class AbortedError extends Error {
  constructor() {
    super('Scan cancelled.')
    this.name = 'AbortedError'
  }
}

/** Upload files and run a scan. Uses XHR (not fetch) so upload progress can
 * be reported to the caller for the progress bar. */
export function runCheck(opts: CheckOptions): RunningCheck {
  const { files, mode, threshold, algorithm, minMatchWords, onProgress } = opts

  const form = new FormData()
  form.append('mode', mode)
  form.append('threshold', String(threshold))
  if (algorithm !== undefined) form.append('algorithm', algorithm)
  if (minMatchWords !== undefined) form.append('min_match_words', String(minMatchWords))
  for (const file of files) form.append('files', file, file.name)

  const xhr = new XMLHttpRequest()

  const promise = new Promise<CheckResponse>((resolve, reject) => {
    xhr.open('POST', `${API_BASE}/api/check`)

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total)
    }

    xhr.onload = () => {
      let body: unknown
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        reject(new Error(`The server answered with an unexpected response (HTTP ${xhr.status}).`))
        return
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as CheckResponse)
      } else if (isErrorBody(body)) {
        reject(new ApiError(body))
      } else {
        reject(new Error(`Scan failed (HTTP ${xhr.status}).`))
      }
    }

    xhr.onabort = () => reject(new AbortedError())
    xhr.onerror = () => reject(new NetworkError())
    xhr.send(form)
  })

  return { promise, abort: () => xhr.abort() }
}
