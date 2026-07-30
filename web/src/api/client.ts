import { ApiError } from './types'
import type {
  ApiErrorBody,
  CheckResponse,
  DetectLanguageResponse,
  Mode,
  PairResponse,
  ReportResponse,
} from './types'

async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  const body = await res.json()
  if (!res.ok) throw new ApiError(body as ApiErrorBody)
  return body as T
}

export async function getModes(): Promise<Mode[]> {
  const res = await fetch('/api/modes')
  const body = await parseJsonOrThrow<{ modes: Mode[] }>(res)
  return body.modes
}

/** Guess the language of a pasted code snippet, for the paste-box UI in
 * code_similarity/ai_code modes. */
export async function detectLanguage(text: string): Promise<DetectLanguageResponse> {
  const res = await fetch('/api/detect-language', {
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
  minMatchWords?: number
  onProgress?: (fraction: number) => void
}

/** Upload files and run a scan. Uses XHR (not fetch) so upload progress can
 * be reported to the caller for the drop zone's progress bar. */
export function runCheck(opts: CheckOptions): Promise<CheckResponse> {
  const { files, mode, threshold, minMatchWords, onProgress } = opts

  const form = new FormData()
  form.append('mode', mode)
  form.append('threshold', String(threshold))
  if (minMatchWords !== undefined) form.append('min_match_words', String(minMatchWords))
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
