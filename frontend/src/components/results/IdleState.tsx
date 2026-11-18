import { motion } from 'motion/react'
import type { Algorithm, Mode, SamplePreset } from '../../api/types'
import { ALGORITHM_LABEL, formatPercent } from '../../lib/format'
import { EASE_OUT } from '../../lib/motion'
import { MODE_EXTENSIONS } from '../DropZone/rules'
import { CodeIcon, PlayIcon, ShieldIcon, TextIcon } from '../icons'

interface IdleStateProps {
  mode: Mode
  threshold: number
  algorithm: Algorithm
  minMatchWords: number
  useDefaultExclusions: boolean
  excludedCount: number
  disabled?: boolean
  onRunSample: (preset: SamplePreset) => void
}

const item = {
  hidden: { opacity: 0, y: 8 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.35, ease: EASE_OUT } },
}

export function IdleState({
  mode,
  threshold,
  algorithm,
  minMatchWords,
  useDefaultExclusions,
  excludedCount,
  disabled,
  onRunSample,
}: IdleStateProps) {
  const isCode = mode === 'code_similarity'

  const pipelineStages = isCode
    ? [
        { step: '01', name: 'Ingest & Sandbox', detail: '.py · .java · .c · .cpp · .zip' },
        { step: '02', name: 'Lexical Strip', detail: 'Strip comments & string literals' },
        { step: '03', name: 'Structural AST', detail: 'Python AST + C/Java identifier norm' },
        { step: '04', name: 'Span Coverage', detail: `${minMatchWords}-word min · 5-gram & block link` },
        { step: '05', name: 'Evidence Matrix', detail: 'Bi-directional diff, clusters & PDF' },
      ]
    : [
        { step: '01', name: 'Dual-Parser Load', detail: 'pdfplumber → PyMuPDF · docx · txt' },
        { step: '02', name: 'NLP Normalize', detail: 'Lowercase · NLTK tokenize · Porter stem' },
        {
          step: '03',
          name: 'Stopword & Excl',
          detail: useDefaultExclusions ? `50 academic terms${excludedCount ? ` + ${excludedCount}` : ''}` : 'NLTK stopwords',
        },
        { step: '04', name: '5-Gram & Index', detail: `${minMatchWords}-word min · Turnitin index` },
        { step: '05', name: 'Evidence Matrix', detail: 'Synced highlights, clusters & PDF' },
      ]

  return (
    <motion.div className="idle" initial="hidden" animate="shown" transition={{ staggerChildren: 0.05 }}>
      <motion.div className="idle-top" variants={item}>
        <p className="eyebrow">{isCode ? 'Structural & lexical code analysis' : 'Local academic similarity workstation'}</p>
        <h2 className="idle-title">
          {isCode ? 'Catch copied logic — even after full identifier renaming.' : 'Transparent, phrase-exact similarity evidence.'}
        </h2>
        <p className="idle-lede">
          {isCode
            ? 'Compares Python abstract syntax trees and normalized C/C++/Java function blocks alongside 5-gram token fingerprints, linking every matched block side by side.'
            : 'Extracts, normalizes, and compares academic submissions locally. Every score maps directly to highlighted passages, per-document source breakdowns, and collusion clusters.'}
        </p>
      </motion.div>

      <motion.div className="idle-demos-section" variants={item}>
        <div className="idle-section-head">
          <span className="idle-section-label">Instant verification suites</span>
          <span className="idle-section-hint">Run built-in benchmark fixtures in one click</span>
        </div>
        <div className="idle-demos">
          <button
            type="button"
            className="demo-card"
            disabled={disabled}
            onClick={() => onRunSample('text')}
          >
            <div className="demo-card-head">
              <span className="demo-icon">
                <TextIcon size={16} />
              </span>
              <span className="demo-badge num">4 files · TXT / PDF / DOCX</span>
            </div>
            <div className="demo-card-body">
              <h3 className="demo-title">Academic Prose & Multi-Format Batch</h3>
              <p className="demo-desc">
                Tests cross-format extraction, 50-term academic boilerplate filtering, Turnitin similarity index, and collusion clustering.
              </p>
            </div>
            <span className="demo-cta">
              <PlayIcon size={13} />
              Run prose demo
            </span>
          </button>

          <button
            type="button"
            className="demo-card"
            disabled={disabled}
            onClick={() => onRunSample('code')}
          >
            <div className="demo-card-head">
              <span className="demo-icon">
                <CodeIcon size={16} />
              </span>
              <span className="demo-badge num">2 files · Python AST</span>
            </div>
            <div className="demo-card-body">
              <h3 className="demo-title">Renamed Identifier Code Plagiarism</h3>
              <p className="demo-desc">
                Tests two Python programs where every variable and function name was disguised — caught via normalized AST structure.
              </p>
            </div>
            <span className="demo-cta">
              <PlayIcon size={13} />
              Run code AST demo
            </span>
          </button>
        </div>
      </motion.div>

      <motion.div className="idle-pipeline-section" variants={item}>
        <div className="idle-section-head">
          <span className="idle-section-label">Active pipeline configuration</span>
          <span className="idle-section-hint num">
            {ALGORITHM_LABEL[algorithm]} · flag ≥ {formatPercent(threshold)} · min {minMatchWords}w
          </span>
        </div>
        <ol className="pipeline-rail">
          {pipelineStages.map((stage) => (
            <li key={stage.step} className="pipeline-node">
              <span className="pipeline-step num">{stage.step}</span>
              <strong className="pipeline-name">{stage.name}</strong>
              <span className="pipeline-detail">{stage.detail}</span>
            </li>
          ))}
        </ol>
      </motion.div>

      <motion.div className="idle-footer" variants={item}>
        <div className="format-chips" aria-label="Accepted formats">
          {MODE_EXTENSIONS[mode].map((ext) => (
            <span key={ext} className="format-chip">
              {ext}
            </span>
          ))}
          <span className="format-chip">.zip</span>
        </div>
        <p className="privacy-note">
          <ShieldIcon />
          100% offline local execution — zero cloud uploads or external APIs.
        </p>
      </motion.div>
    </motion.div>
  )
}
