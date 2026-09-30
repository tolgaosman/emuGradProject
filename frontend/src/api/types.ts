export type Mode = 'code_similarity' | 'text_similarity'
export type Language = 'text' | 'python' | 'java' | 'c' | 'cpp'
export type Algorithm = 'auto' | 'cosine' | 'winnowing' | 'jaccard' | 'ast'

export interface AlgorithmsResponse {
  algorithms: Algorithm[]
  by_mode: Record<Mode, Algorithm[]>
}

export type StorageBackend = 'postgres' | 'json'

export interface StatusResponse {
  status: string
  service: string
  version: string
  uptime_s?: number
  offline?: boolean
  storage?: StorageBackend
}

export interface SimilarityPair {
  file_a: string
  file_b: string
  score: number
  flagged: boolean
  /** Distinct shared 5-grams (report FR-10). Absent on scans stored in PostgreSQL. */
  matched_kgrams?: number
}

export interface ScanMatrix {
  names: string[]
  scores: number[][]
}

export interface FileError {
  file: string
  error: string
}

export interface SourceContribution {
  source: string
  contribution: number
  spans: [number, number][]
}

export interface ScanFileInfo {
  name: string
  /** Position in the uploaded batch, so the reference (index 0) is found by
   * position rather than by a name the server may have sanitized. */
  index: number
  language: Language
  size_bytes: number
  word_count: number
}

export interface ScanSummary {
  pair_count: number
  flagged_count: number
  max_score: number
  mean_score: number
}

export interface CheckResponse {
  scan_id: string
  mode: Mode
  algorithm: Algorithm
  threshold: number
  min_match_words: number
  matrix: ScanMatrix | null
  pairs: SimilarityPair[]
  similarity_indices: Record<string, number>
  source_breakdowns: Record<string, SourceContribution[]>
  errors: FileError[]
  summary?: ScanSummary
  files?: ScanFileInfo[]
  duration_s?: number
}

export interface ApiErrorBody {
  error: string
  code: string
  choices?: string[]
  scan_id?: string
  file_errors?: FileError[]
}

export class ApiError extends Error {
  code: string
  body: ApiErrorBody

  constructor(body: ApiErrorBody) {
    super(body.error)
    this.name = 'ApiError'
    this.code = body.code
    this.body = body
  }
}

export interface ScanFileMeta {
  file_name: string
  file_size_bytes: number
  file_format: string
  similarity_index?: number | null
}

/** `GET /api/report/<uuid>`. `algorithm` is the legacy name for the mode;
 * the forced algorithm lives in `algorithm_override`. */
export interface ReportResponse {
  scan_uuid: string
  scan_id: string
  algorithm: Mode
  mode: Mode
  algorithm_override: Algorithm
  threshold: number
  min_match_words: number
  status: string
  timestamp: string
  files: ScanFileMeta[]
  pairs: SimilarityPair[]
  matrix: ScanMatrix
  similarity_indices: Record<string, number>
  source_breakdowns: Record<string, SourceContribution[]>
  comparison_available: boolean
}

export interface ScanHistoryEntry {
  scan_uuid: string
  timestamp: string
  mode: Mode
  threshold: number
  file_names: string[]
  max_score: number | null
  flagged_count: number
}

export interface PairSide {
  name: string
  text: string
  matched_spans: [number, number][]
}

export interface PairResponse {
  file_a: PairSide
  file_b: PairSide
  matched_kgrams?: number
  min_match_words?: number
}

export interface DetectLanguageResponse {
  language: Language
  confidence: number
}
