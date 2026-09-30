import type { Language, Mode } from '../../api/types'
import { extensionOf } from '../../lib/format'

/** Client-side mirrors of `backend/src/loader.py` — change both together. */
export const MAX_BYTES = 10 * 1024 * 1024
export const MAX_FILES = 50
export const PASTE_CHAR_LIMIT = 15_000

export const MODE_EXTENSIONS: Record<Mode, readonly string[]> = {
  text_similarity: ['.txt', '.pdf', '.docx'],
  code_similarity: ['.py', '.java', '.c', '.h', '.cpp', '.cc', '.hpp'],
}

export const LANGUAGE_EXTENSION: Record<Language, string> = {
  text: '.txt',
  python: '.py',
  java: '.java',
  c: '.c',
  cpp: '.cpp',
}

export interface FileRejection {
  name: string
  reason: string
}

interface ValidateOptions {
  mode: Mode
  existingCount: number
  maxFiles: number
}

/** Split `candidates` into files the server will accept and the rest, with a
 * human-readable reason for each rejection. */
export function validateFiles(
  candidates: readonly File[],
  { mode, existingCount, maxFiles }: ValidateOptions,
): { accepted: File[]; rejections: FileRejection[] } {
  const extensions = MODE_EXTENSIONS[mode]
  const accepted: File[] = []
  const rejections: FileRejection[] = []
  let count = existingCount

  for (const file of candidates) {
    const ext = extensionOf(file.name)
    let reason: string | null = null
    if (!extensions.includes(ext)) {
      reason = `${ext || 'This format'} isn’t accepted in ${mode === 'text_similarity' ? 'Text' : 'Code'} mode`
    } else if (file.size === 0) {
      reason = 'The file is empty'
    } else if (file.size > MAX_BYTES) {
      reason = 'Larger than the 10 MB limit'
    } else if (count >= maxFiles) {
      reason = maxFiles === 1 ? 'Only one file fits here' : `The ${maxFiles}-file limit is reached`
    }

    if (reason) {
      rejections.push({ name: file.name, reason })
    } else {
      accepted.push(file)
      count += 1
    }
  }
  return { accepted, rejections }
}

/** Short format badge for a file row: "PDF", "DOCX", "PY", … */
export function formatBadge(name: string): string {
  return extensionOf(name).slice(1).toUpperCase() || 'FILE'
}
