import { useCallback, useEffect, useState } from 'react'
import { flushSync } from 'react-dom'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'plagcheck-theme'

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function readStoredTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    return stored === 'light' || stored === 'dark' ? stored : null
  } catch {
    return null
  }
}

function storeTheme(theme: Theme) {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // Private mode or blocked storage: the choice just won't persist.
  }
}

/** Tracks the active theme. index.html resolves it before first paint; this
 * hook keeps `data-theme` in sync, persists explicit choices, and follows the
 * OS preference live until the user makes one. */
export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const [theme, setTheme] = useState<Theme>(() => readStoredTheme() ?? systemTheme())

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    const mql = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => {
      // Re-checked per event: once the user picks a theme, OS changes stop
      // overriding it.
      if (!readStoredTheme()) setTheme(systemTheme())
    }
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])

  const toggleTheme = useCallback(() => {
    const apply = () => {
      setTheme((prev) => {
        const next: Theme = prev === 'dark' ? 'light' : 'dark'
        storeTheme(next)
        document.documentElement.dataset.theme = next
        return next
      })
    }
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    // Cross-fade the whole page where supported, instead of every surface
    // snapping (or transitioning at its own pace) independently.
    if (!document.startViewTransition || reduceMotion) {
      apply()
      return
    }
    document.startViewTransition(() => flushSync(apply))
  }, [])

  return { theme, toggleTheme }
}
