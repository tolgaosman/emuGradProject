import { useEffect, useState } from 'react'
import { getStatus } from '../api/client'
import type { Mode } from '../api/types'
import lightModeLogo from '../assets/lightModeLogo.png'

interface SidebarEntry {
  mode: Mode
  label: string
  icon: string
}

const GROUPS: { heading: string; entries: SidebarEntry[] }[] = [
  {
    heading: 'Text',
    entries: [{ mode: 'text_similarity', label: 'Similarity Check', icon: '📖' }],
  },
  {
    heading: 'Code',
    entries: [{ mode: 'code_similarity', label: 'Similarity Check', icon: '⧉' }],
  },
]

interface SidebarProps {
  mode: Mode
  onModeChange: (mode: Mode) => void
  disabled?: boolean
}

export function Sidebar({ mode, onModeChange, disabled }: SidebarProps) {
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false
    getStatus()
      .then(() => {
        if (!cancelled) setApiOnline(true)
      })
      .catch(() => {
        if (!cancelled) setApiOnline(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <img
          src={lightModeLogo}
          alt="PlagCheck"
          className="sidebar-logo"
        />
        <span className="sidebar-name">PlagCheck</span>
      </div>

      <nav className="sidebar-nav" aria-label="Scanning mode">
        {GROUPS.map((group) => (
          <div className="sidebar-group" key={group.heading}>
            <p className="sidebar-group-heading">{group.heading}</p>
            {group.entries.map((entry) => (
              <button
                key={entry.mode}
                type="button"
                role="radio"
                aria-checked={mode === entry.mode}
                className={`sidebar-item${mode === entry.mode ? ' sidebar-item-active' : ''}`}
                disabled={disabled}
                onClick={() => onModeChange(entry.mode)}
              >
                <span className="sidebar-item-icon" aria-hidden="true">
                  {entry.icon}
                </span>
                {entry.label}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <span className={`sidebar-status${apiOnline === false ? ' sidebar-status-offline' : ''}`}>
          <span className="sidebar-status-dot" aria-hidden="true" />
          {apiOnline === false ? 'API offline' : apiOnline === null ? 'Checking…' : 'System Ready'}
        </span>
      </div>
    </aside>
  )
}
