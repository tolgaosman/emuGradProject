import { AnimatePresence, motion } from 'motion/react'
import type { Mode } from '../api/types'
import type { ApiStatus } from '../hooks/useApiStatus'
import type { Theme } from '../hooks/useTheme'
import { fade } from '../lib/motion'
import { BrandMark } from './BrandMark'
import { CodeIcon, HistoryIcon, MoonIcon, RefreshIcon, SunIcon, TextIcon } from './icons'
import { Segmented } from './Segmented'

const MODE_OPTIONS = [
  { value: 'text_similarity', label: 'Text', icon: <TextIcon /> },
  { value: 'code_similarity', label: 'Code', icon: <CodeIcon /> },
] as const

interface HeaderProps {
  mode: Mode
  onModeChange: (mode: Mode) => void
  modeLocked: boolean
  theme: Theme
  onToggleTheme: () => void
  apiStatus: ApiStatus
  onRetryStatus: () => void
  onOpenHistory: () => void
}

export function Header({
  mode,
  onModeChange,
  modeLocked,
  theme,
  onToggleTheme,
  apiStatus,
  onRetryStatus,
  onOpenHistory,
}: HeaderProps) {
  return (
    <header className="app-header">
      <div className="app-header-inner">
        <div className="brand">
          <BrandMark size={26} />
          <span className="brand-name">PlagCheck</span>
        </div>

        <Segmented
          id="mode"
          label="Document type"
          options={MODE_OPTIONS}
          value={mode}
          onChange={onModeChange}
          disabled={modeLocked}
        />

        <div className="app-header-actions">
          <StatusPill status={apiStatus} onRetry={onRetryStatus} />
          <button type="button" className="btn btn-ghost btn-sm" onClick={onOpenHistory}>
            <HistoryIcon />
            <span className="hide-narrow">History</span>
          </button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </div>
    </header>
  )
}

function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const dark = theme === 'dark'
  return (
    <button
      type="button"
      className="icon-btn"
      aria-label="Dark theme"
      aria-pressed={dark}
      title={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      onClick={onToggle}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={theme}
          className="icon-swap"
          initial={{ opacity: 0, rotate: -60, scale: 0.6 }}
          animate={{ opacity: 1, rotate: 0, scale: 1 }}
          exit={{ opacity: 0, rotate: 60, scale: 0.6 }}
          transition={fade}
        >
          {dark ? <MoonIcon /> : <SunIcon />}
        </motion.span>
      </AnimatePresence>
    </button>
  )
}

function StatusPill({ status, onRetry }: { status: ApiStatus; onRetry: () => void }) {
  const label =
    status.state === 'online'
      ? status.storage === 'postgres'
        ? 'Local · PostgreSQL'
        : 'Local · file storage'
      : status.state === 'offline'
        ? 'Server unreachable'
        : 'Connecting…'

  return (
    <div className="status-pill" data-state={status.state} role="status" aria-live="polite">
      <span className="status-dot" aria-hidden="true" />
      <span className="hide-narrow">{label}</span>
      {status.state === 'offline' && (
        <button
          type="button"
          className="status-retry"
          onClick={onRetry}
          aria-label="Retry connecting to the server"
        >
          <RefreshIcon size={13} />
        </button>
      )}
    </div>
  )
}
