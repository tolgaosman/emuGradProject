import { motion } from 'motion/react'
import type { Mode, SamplePreset } from '../../api/types'
import { EASE_OUT } from '../../lib/motion'
import { CodeIcon, PlayIcon, ShieldIcon, TextIcon } from '../icons'

interface IdleStateProps {
  mode: Mode
  disabled?: boolean
  onRunSample: (preset: SamplePreset) => void
}

const item = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.3, ease: EASE_OUT } },
}

export function IdleState({ mode, disabled, onRunSample }: IdleStateProps) {
  const isCode = mode === 'code_similarity'

  return (
    <motion.div className="idle" initial="hidden" animate="shown" transition={{ staggerChildren: 0.05 }}>
      <div className="idle-center">
        <motion.h2 className="idle-title" variants={item}>
          {isCode ? 'Compare source code' : 'Compare documents'}
        </motion.h2>
        <motion.p className="idle-lede" variants={item}>
          {isCode
            ? 'Drop Python, Java, C, or C++ files on the left — or try a sample set.'
            : 'Drop PDF, Word, or text files on the left — or try a sample set.'}
        </motion.p>

        <motion.div className="idle-demos" variants={item}>
          <button
            type="button"
            className="demo-card"
            disabled={disabled}
            onClick={() => onRunSample('text')}
          >
            <span className="demo-icon">
              <TextIcon size={16} />
            </span>
            <span className="demo-card-text">
              <strong className="demo-title">Prose sample</strong>
              <span className="demo-meta num">4 files · TXT, PDF, DOCX</span>
            </span>
            <span className="demo-play" aria-hidden="true">
              <PlayIcon size={13} />
            </span>
          </button>

          <button
            type="button"
            className="demo-card"
            disabled={disabled}
            onClick={() => onRunSample('code')}
          >
            <span className="demo-icon">
              <CodeIcon size={16} />
            </span>
            <span className="demo-card-text">
              <strong className="demo-title">Code AST sample</strong>
              <span className="demo-meta num">2 files · Python rename</span>
            </span>
            <span className="demo-play" aria-hidden="true">
              <PlayIcon size={13} />
            </span>
          </button>
        </motion.div>

        <motion.p className="privacy-note" variants={item}>
          <ShieldIcon size={14} />
          Offline local execution
        </motion.p>
      </div>
    </motion.div>
  )
}
