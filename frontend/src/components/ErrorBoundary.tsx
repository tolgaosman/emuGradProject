import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { AlertIcon } from './icons'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('PlagCheck UI crashed:', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <main className="crash">
        <div className="error-state" role="alert">
          <span className="error-state-icon" aria-hidden="true">
            <AlertIcon size={20} />
          </span>
          <h1 className="error-state-title">Something went wrong</h1>
          <p className="error-state-body">
            The interface hit an unexpected error. Your scans are saved — reloading usually fixes it.
          </p>
          <div className="error-state-actions">
            <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
              Reload
            </button>
          </div>
        </div>
      </main>
    )
  }
}
