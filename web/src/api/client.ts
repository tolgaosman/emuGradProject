import { ApiError } from './types'
import type {
  Algorithm,
  AlgorithmsResponse,
  ApiErrorBody,
  CheckResponse,
  DetectLanguageResponse,
  Mode,
  PairResponse,
  StatusResponse,
} from './types'

async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  const body = await res.json()
  if (!res.ok) throw new ApiError(body as ApiErrorBody)
  return body as T
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

/** Algorithm choices selectable per mode, for the ALGORITHM chip row. */
export async function getAlgorithms(): Promise<AlgorithmsResponse> {
  const res = await fetch(`${API_BASE}/api/algorithms`)
  return parseJsonOrThrow<AlgorithmsResponse>(res)
}

/** Liveness check, for the top bar's "System Ready" indicator. */
export async function getStatus(): Promise<StatusResponse> {
  const res = await fetch(`${API_BASE}/api/status`)
  return parseJsonOrThrow<StatusResponse>(res)
}

/** Guess the language of a pasted code snippet, for the paste-box UI in
 * code_similarity mode. */
export async function detectLanguage(text: string): Promise<DetectLanguageResponse> {
  const res = await fetch(`${API_BASE}/api/detect-language`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  return parseJsonOrThrow<DetectLanguageResponse>(res)
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
 * be reported to the caller for the drop zone's progress bar. */
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
        reject(new Error('Server returned an invalid response.'))
        return
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as CheckResponse)
      } else {
        reject(new ApiError(body as ApiErrorBody))
      }
    }

    xhr.onabort = () => reject(new AbortedError())
    xhr.onerror = () => reject(new Error('Network error — is the PlagCheck API running?'))
    xhr.send(form)
  })

  return { promise, abort: () => xhr.abort() }
}

/** Both files' text plus the matched-span offsets to highlight.
 *
 * `minMatchWords` defaults server-side to whatever the scan was run with, so
 * the highlighting matches the score being displayed; pass it only to
 * explore a different threshold.
 */
export async function getPair(
  scanId: string,
  fileA: string,
  fileB: string,
  minMatchWords?: number,
): Promise<PairResponse> {
  const query = minMatchWords === undefined ? '' : `?min_match_words=${minMatchWords}`
  const res = await fetch(
    `${API_BASE}/api/report/${encodeURIComponent(scanId)}/pair/${encodeURIComponent(fileA)}/${encodeURIComponent(fileB)}${query}`,
  )
  return parseJsonOrThrow<PairResponse>(res)
}

/** Server-rendered PDF of one comparison, with both documents reproduced in
 * full and the matched regions highlighted — the printable form of what
 * `ComparisonInspector` shows on screen.
 *
 * Like `getPair`, `minMatchWords` defaults server-side to the scan's own
 * value so the PDF can't highlight more than the score counted. */
export function pairPdfUrl(
  scanId: string,
  fileA: string,
  fileB: string,
  minMatchWords?: number,
): string {
  const query = minMatchWords === undefined ? '' : `?min_match_words=${minMatchWords}`
  return `${API_BASE}/api/report/${encodeURIComponent(scanId)}/pair-pdf/${encodeURIComponent(fileA)}/${encodeURIComponent(fileB)}${query}`
}

/** Server-rendered 300 DPI heatmap, for downloading the scan as an image. */
export function heatmapUrl(scanId: string, ref?: string): string {
  const query = ref ? `?ref=${encodeURIComponent(ref)}` : ''
  return `${API_BASE}/api/report/${encodeURIComponent(scanId)}/heatmap.png${query}`
}
