import { motion } from 'motion/react'
import type { Mode } from '../../api/types'
import type { Workspace } from '../../lib/deriveResults'
import { EASE_OUT } from '../../lib/motion'
import { MODE_EXTENSIONS } from '../DropZone/rules'
import { ShieldIcon } from '../icons'

interface IdleStateProps {
  mode: Mode
  workspace: Workspace
}

const item = {
  hidden: { opacity: 0, y: 8 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE_OUT } },
}

export function IdleState({ mode, workspace }: IdleStateProps) {
  const isCode = mode === 'code_similarity'
  const steps = [
    {
      title: 'Add documents',
      body:
        workspace === 'one-to-many'
          ? 'Pick the document to check, then the ones to check it against.'
          : 'Drop in every submission; each one is compared with all the others.',
    },
    {
      title: 'Set the review threshold',
      body: 'Pairs at or above it are flagged for a closer look — never an automatic verdict.',
    },
    {
      title: 'Inspect the evidence',
      body: 'Open any pair to see matching passages side by side, then export a PDF, CSV or HTML report.',
    },
  ]

  return (
    <motion.div className="idle" initial="hidden" animate="shown" transition={{ staggerChildren: 0.06 }}>
      <motion.p className="eyebrow" variants={item}>
        {isCode ? 'Source code similarity' : 'Document similarity'}
      </motion.p>
      <motion.h2 className="idle-title" variants={item}>
        {isCode ? 'Find copied code, even when it’s been renamed.' : 'See exactly where documents overlap.'}
      </motion.h2>
      <motion.p className="idle-lede" variants={item}>
        {isCode
          ? 'Python, Java, C and C++ are compared token by token, and Python files structurally, so renamed variables don’t hide a copy.'
          : 'Essays, reports and assignments are normalised, stemmed and compared phrase by phrase. Every match is highlighted in context.'}
      </motion.p>

      <motion.ol className="steps" variants={item}>
        {steps.map((step, i) => (
          <li key={step.title} className="step">
            <span className="step-number num" aria-hidden="true">
              {i + 1}
            </span>
            <div>
              <h3 className="step-title">{step.title}</h3>
              <p className="step-body">{step.body}</p>
            </div>
          </li>
        ))}
      </motion.ol>

      <motion.div className="idle-footer" variants={item}>
        <div className="format-chips" aria-label="Accepted formats">
          {MODE_EXTENSIONS[mode].map((ext) => (
            <span key={ext} className="format-chip">
              {ext}
            </span>
          ))}
        </div>
        <p className="privacy-note">
          <ShieldIcon />
          Runs entirely on this machine. Documents never leave it.
        </p>
      </motion.div>
    </motion.div>
  )
}
