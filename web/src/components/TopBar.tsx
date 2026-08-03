import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { getStatus } from '../api/client'
import type { Mode } from '../api/types'
import type { Theme } from '../hooks/useTheme'
import darkModeLogo from '../assets/darkModeLogo.png'
import lightModeLogo from '../assets/lightModeLogo.png'

const STATUS_POLL_MS = 15_000

interface ModeOption {
  mode: Mode
  label: string
}

const MODE_OPTIONS: ModeOption[] = [
  { mode: 'text_similarity', label: 'Text' },
  { mode: 'code_similarity', label: 'Code' },
]

interface TopBarProps {
  mode: Mode
  onModeChange: (mode: Mode) => void
  disabled?: boolean
  theme: Theme
  onToggleTheme: () => void
}

export function TopBar({ mode, onModeChange, disabled, theme, onToggleTheme }: TopBarProps) {
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)
  const [scrolled, setScrolled] = useState(false)
  const groupRef = useRef<HTMLDivElement>(null)
  const activeIndex = MODE_OPTIONS.findIndex((o) => o.mode === mode)

  useEffect(() => {
    let cancelled = false
    const check = () => {
      getStatus()
        .then(() => {
          if (!cancelled) setApiOnline(true)
        })
        .catch(() => {
          if (!cancelled) setApiOnline(false)
        })
    }
    check()
    const id = window.setInterval(check, STATUS_POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 0)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const handleKeyDown = (e: KeyboardEvent) => {
    if (disabled) return
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const dir = e.key === 'ArrowRight' ? 1 : -1
      const next = MODE_OPTIONS[(activeIndex + dir + MODE_OPTIONS.length) % MODE_OPTIONS.length]
      onModeChange(next.mode)
    }
  }

  return (
    <header className={`topbar${scrolled ? ' topbar-scrolled' : ''}`}>
      <div className="topbar-zone topbar-brand">
        <img
          src={theme === 'dark' ? darkModeLogo : lightModeLogo}
          alt="PlagCheck"
          className="topbar-logo"
        />
      </div>

      <div
        className="topbar-zone topbar-switch-zone"
        role="radiogroup"
        aria-label="Scanning mode"
        ref={groupRef}
        onKeyDown={handleKeyDown}
      >
        <div className="topbar-switch">
          <span
            className="topbar-switch-thumb"
            style={{ transform: `translateX(${activeIndex * 100}%)` }}
            aria-hidden="true"
          />
          {MODE_OPTIONS.map((option) => (
            <button
              key={option.mode}
              type="button"
              role="radio"
              aria-checked={mode === option.mode}
              className={`topbar-switch-btn${mode === option.mode ? ' topbar-switch-btn-active' : ''}`}
              disabled={disabled}
              onClick={() => onModeChange(option.mode)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="topbar-zone topbar-right">
        <button
          type="button"
          className="topbar-theme-toggle"
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          onClick={onToggleTheme}
        >
          {theme === 'dark' ? '☀' : '☾'}
        </button>

        <span
          className={`topbar-status${apiOnline === false ? ' topbar-status-offline' : ''}`}
          title={apiOnline === false ? 'Backend unreachable — run `npm run api`' : undefined}
        >
          <span className="topbar-status-dot" aria-hidden="true" />
          {apiOnline === false ? 'API offline' : apiOnline === null ? 'Checking…' : 'System Ready'}
        </span>
      </div>
    </header>
  )
}
