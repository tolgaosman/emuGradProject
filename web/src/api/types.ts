export type Algorithm = 'cosine' | 'winnowing' | 'jaccard' | 'ast' | 'all'

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

export interface CheckResponse {
  scan_id: string
  algorithm: Algorithm
  threshold: number
  matrix: ScanMatrix
  pairs: SimilarityPair[]
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
}

export interface ReportResponse {
  scan_uuid: string
  algorithm: Algorithm
  threshold: number
  status: string
  timestamp: string
  files: ScanFileMeta[]
  pairs: SimilarityPair[]
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
