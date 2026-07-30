export type Mode = 'code_similarity' | 'text_similarity' | 'ai_code' | 'ai_text'
export type Language = 'text' | 'python' | 'java' | 'c' | 'cpp'
export type AIBand = 'low' | 'possible' | 'likely'
export type Algorithm = 'auto' | 'cosine' | 'winnowing' | 'jaccard' | 'ast'

export interface AlgorithmsResponse {
  algorithms: Algorithm[]
  by_mode: Record<Mode, Algorithm[]>
}

export interface StatusResponse {
  status: string
  service: string
  version: string
}

export interface SimilarityPair {
  file_a: string
  file_b: string
  score: number
  flagged: boolean
}

export interface ScanMatrix {
  names: string[]
  scores: number[][]
}

export interface FileError {
  file: string
  error: string
}

export interface AISignal {
  name: string
  score: number
  weight: number
}

export interface AISegment {
  start: number
  end: number
  probability: number
}

export interface AIScore {
  file: string
  overall_probability: number
  band: AIBand
  signals: AISignal[]
  segments: AISegment[]
}

export interface SourceContribution {
  source: string
  contribution: number
  spans: [number, number][]
}

/** One fetched web page compared against an uploaded file, from the
 * "compare against the internet" feature (code_similarity/text_similarity
 * only — see plagcheck/src/websearch.py). */
export interface WebMatch {
  query: string
  url: string
  title: string
  score: number
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
  web_matches: Record<string, WebMatch[]>
  /** True when include_web defaulted to on but the server has no
   * WEB_SEARCH_API_KEY/WEB_SEARCH_ENGINE_ID configured — the scan still
   * completed, just without internet comparison. */
  web_search_unavailable: boolean
  ai_scores: AIScore[]
  errors: FileError[]
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

export interface ReportResponse {
  scan_uuid: string
  algorithm: Mode
  threshold: number
  status: string
  timestamp: string
  files: ScanFileMeta[]
  pairs: SimilarityPair[]
  ai_scores: AIScore[]
  source_breakdowns: Record<string, SourceContribution[]>
}

export interface PairSide {
  name: string
  text: string
  matched_spans: [number, number][]
}

export interface PairResponse {
  file_a: PairSide
  file_b: PairSide
}

export interface DetectLanguageResponse {
  language: Language
  confidence: number
}
