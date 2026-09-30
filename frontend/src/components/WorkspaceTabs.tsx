import { motion } from 'motion/react'
import { useRef } from 'react'
import type { KeyboardEvent } from 'react'
import type { Workspace } from '../lib/deriveResults'
import { spring } from '../lib/motion'

const WORKSPACES: readonly { value: Workspace; label: string; description: string }[] = [
  {
    value: 'one-to-many',
    label: 'One vs many',
    description: 'Check one document against several others.',
  },
  {
    value: 'batch',
    label: 'Batch · class',
    description: 'Compare every submission against every other.',
  },
]

interface WorkspaceTabsProps {
  value: Workspace
  onChange: (workspace: Workspace) => void
  disabled?: boolean
}

export function WorkspaceTabs({ value, onChange, disabled }: WorkspaceTabsProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const activeIndex = WORKSPACES.findIndex((w) => w.value === value)
  const active = WORKSPACES[activeIndex]

  const handleKeyDown = (e: KeyboardEvent) => {
    if (disabled || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return
    e.preventDefault()
    const next = (activeIndex + (e.key === 'ArrowRight' ? 1 : -1) + WORKSPACES.length) % WORKSPACES.length
    onChange(WORKSPACES[next].value)
    refs.current[next]?.focus()
  }

  return (
    <div className="workspace-bar">
      <div className="workspace-tabs" role="tablist" aria-label="Comparison layout" onKeyDown={handleKeyDown}>
        {WORKSPACES.map((workspace, i) => {
          const selected = workspace.value === value
          return (
            <button
              key={workspace.value}
              ref={(el) => {
                refs.current[i] = el
              }}
              type="button"
              role="tab"
              id={`workspace-tab-${workspace.value}`}
              aria-selected={selected}
              aria-controls="workspace-panel"
              tabIndex={selected ? 0 : -1}
              className="workspace-tab"
              disabled={disabled}
              onClick={() => onChange(workspace.value)}
            >
              {workspace.label}
              {selected && (
                <motion.span
                  layoutId="workspace-underline"
                  className="workspace-underline"
                  transition={spring.snappy}
                  aria-hidden="true"
                />
              )}
            </button>
          )
        })}
      </div>
      <p className="workspace-description">{active.description}</p>
    </div>
  )
}
