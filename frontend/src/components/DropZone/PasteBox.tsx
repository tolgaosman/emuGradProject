import { useEffect, useEffectEvent, useId, useRef, useState } from 'react'
import { detectLanguage } from '../../api/client'
import type { Language, Mode } from '../../api/types'
import { LANGUAGE_LABEL } from '../../lib/format'
import { LANGUAGE_EXTENSION, PASTE_CHAR_LIMIT } from './rules'

const DETECT_DEBOUNCE_MS = 400
const SYNC_DEBOUNCE_MS = 250
/** Used when detection fails, so a code paste still becomes a scannable file. */
const FALLBACK_LANGUAGE: Language = 'python'
const CODE_LANGUAGES: readonly Language[] = ['python', 'java', 'c', 'cpp']

interface Detection {
  language: Language
  confidence: number | null
}

interface PasteBoxProps {
  mode: Mode
  disabled?: boolean
  /** Receives the paste as a file whenever it settles, or null once cleared. */
  onChange: (file: File | null) => void
}

/** A textarea whose content is scanned as a file — no separate "add" step.
 * In code mode the language is detected (offline heuristic on the server)
 * so the right tokenizer runs; the user can override the guess. */
export function PasteBox({ mode, disabled, onChange }: PasteBoxProps) {
  const [text, setText] = useState('')
  const [detection, setDetection] = useState<Detection | null>(null)
  const [detecting, setDetecting] = useState(false)
  const [override, setOverride] = useState<Language | null>(null)
  const detectSeq = useRef(0)
  const publish = useEffectEvent((file: File | null) => onChange(file))
  const textareaId = useId()

  const isCode = mode === 'code_similarity'
  const hasText = text.trim().length > 0
  const language: Language | null = isCode ? (override ?? detection?.language ?? null) : 'text'

  // Detect the language shortly after typing pauses. The sequence number
  // drops a slow response that lands after a newer one.
  useEffect(() => {
    if (!isCode || !hasText) return
    const id = window.setTimeout(() => {
      const mine = ++detectSeq.current
      setDetecting(true)
      detectLanguage(text)
        .then((res) => {
          if (mine === detectSeq.current) setDetection({ language: res.language, confidence: res.confidence })
        })
        .catch(() => {
          if (mine === detectSeq.current) setDetection({ language: FALLBACK_LANGUAGE, confidence: null })
        })
        .finally(() => {
          if (mine === detectSeq.current) setDetecting(false)
        })
    }, DETECT_DEBOUNCE_MS)
    return () => window.clearTimeout(id)
  }, [text, isCode, hasText])

  // Publish the paste as a file once it settles (and once, in code mode, the
  // language is known — otherwise it would briefly carry the wrong extension).
  useEffect(() => {
    if (!hasText) {
      publish(null)
      return
    }
    if (language === null) return
    const id = window.setTimeout(() => {
      const name = `pasted-${isCode ? 'code' : 'text'}${LANGUAGE_EXTENSION[language]}`
      publish(new File([text], name, { type: 'text/plain' }))
    }, SYNC_DEBOUNCE_MS)
    return () => window.clearTimeout(id)
  }, [text, language, hasText, isCode])

  const languageNote = (() => {
    if (!isCode || !hasText) return null
    if (override) return `Using ${LANGUAGE_LABEL[override]}`
    if (detecting || !detection) return 'Detecting language…'
    if (detection.confidence === null) {
      return `Couldn’t detect — assuming ${LANGUAGE_LABEL[detection.language]}`
    }
    return `${LANGUAGE_LABEL[detection.language]} · ${Math.round(detection.confidence * 100)}% sure`
  })()

  return (
    <div className="paste-box">
      <label htmlFor={textareaId} className="visually-hidden">
        {isCode ? 'Paste source code' : 'Paste text'}
      </label>
      <textarea
        id={textareaId}
        className="textarea"
        value={text}
        onChange={(e) => setText(e.target.value.slice(0, PASTE_CHAR_LIMIT))}
        disabled={disabled}
        placeholder={isCode ? 'Paste source code…' : 'Paste text…'}
        maxLength={PASTE_CHAR_LIMIT}
        spellCheck={!isCode}
      />
      <div className="paste-box-footer">
        <span className="num">
          {text.length.toLocaleString()} / {PASTE_CHAR_LIMIT.toLocaleString()}
          {languageNote && <span className="paste-box-language"> · {languageNote}</span>}
        </span>
        {isCode && (
          <select
            className="select select-sm"
            aria-label="Language of the pasted code"
            value={override ?? ''}
            disabled={disabled || !hasText}
            onChange={(e) => setOverride((e.target.value || null) as Language | null)}
          >
            <option value="">Auto-detect</option>
            {CODE_LANGUAGES.map((lang) => (
              <option key={lang} value={lang}>
                {LANGUAGE_LABEL[lang]}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  )
}
