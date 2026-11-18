import { AnimatePresence, motion } from 'motion/react'
import { useId, useState } from 'react'
import type { Algorithm, AlgorithmScores } from '../../api/types'
import { formatPercent } from '../../lib/format'
import { EASE_OUT } from '../../lib/motion'

interface AlgorithmMeta {
  label: string
  summary: string
  description: string
}

const ALGORITHM_DEFINITIONS: Record<Algorithm, AlgorithmMeta> = {
  auto: {
    label: 'Coverage',
    summary: 'How much of the text is directly shared',
    description:
      'Finds matching phrases (or matching code blocks) and measures what percentage of the document is highlighted below.',
  },
  ast: {
    label: 'AST Structure',
    summary: 'Same code logic, even if renamed',
    description:
      'Ignores variable and function names and checks whether both files use the same loops, conditions, and code structure.',
  },
  cosine: {
    label: 'TF-IDF Cosine',
    summary: 'Similar key words and topic',
    description:
      'Checks if both files use the same important words in similar proportions, even when sentences are reordered or reworded.',
  },
  winnowing: {
    label: 'Winnowing',
    summary: 'Spot-check for copied phrases',
    description:
      'Picks short 5-word snippets throughout each document and checks how many of those exact snippets appear in both files.',
  },
  jaccard: {
    label: 'Jaccard',
    summary: 'Overlap in unique words used',
    description:
      'Compares the list of distinct words in both files — high when they share the same vocabulary, regardless of word order.',
  },
}

interface AlgorithmStripProps {
  scores: AlgorithmScores
  active: Algorithm
  onSelect: (algo: Algorithm) => void
}

export function AlgorithmStrip({ scores, active, onSelect }: AlgorithmStripProps) {
  const [hovered, setHovered] = useState<Algorithm | null>(null)
  const baseId = useId()

  const items: { key: Algorithm; value: number }[] = [
    { key: 'auto', value: scores.coverage },
    ...(scores.ast !== null ? [{ key: 'ast' as const, value: scores.ast }] : []),
    { key: 'cosine', value: scores.cosine },
    { key: 'winnowing', value: scores.winnowing },
    { key: 'jaccard', value: scores.jaccard },
  ]

  return (
    <div className="inspector-subbar">
      <div className="algo-strip" aria-label="Algorithm scores">
        {items.map((item) => {
          const meta = ALGORITHM_DEFINITIONS[item.key]
          const isActive = item.key === active
          const isOpen = hovered === item.key
          const tipId = `${baseId}-${item.key}`

          return (
            <div
              key={item.key}
              className="algo-chip-wrap"
              onMouseEnter={() => setHovered(item.key)}
              onMouseLeave={() => setHovered((cur) => (cur === item.key ? null : cur))}
            >
              <button
                type="button"
                className="algo-chip num"
                data-active={isActive || undefined}
                aria-pressed={isActive}
                aria-describedby={isOpen ? tipId : undefined}
                onFocus={() => setHovered(item.key)}
                onBlur={() => setHovered((cur) => (cur === item.key ? null : cur))}
                onClick={() => onSelect(item.key)}
              >
                <span className="algo-chip-name">{meta.label}</span>
                <strong>{formatPercent(item.value)}</strong>
              </button>

              <AnimatePresence>
                {isOpen && (
                  <motion.div
                    id={tipId}
                    role="tooltip"
                    className="algo-popover"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 3, transition: { duration: 0.1 } }}
                    transition={{ duration: 0.14, ease: EASE_OUT }}
                  >
                    <div className="algo-popover-head">
                      <span className="algo-popover-title">{meta.summary}</span>
                      <span className="algo-popover-score num">{formatPercent(item.value)}</span>
                    </div>
                    <p className="algo-popover-desc">{meta.description}</p>
                    <span className="algo-popover-hint">
                      {isActive ? 'Shown in the panes below' : 'Click to highlight what this checks'}
                    </span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )
        })}
      </div>
    </div>
  )
}
