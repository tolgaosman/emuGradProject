import type { FileError } from '../../api/types'
import { AlertIcon, RefreshIcon } from '../icons'

const COPY: Record<string, { title: string; body: string }> = {
  network: {
    title: 'Can’t reach the PlagCheck server',
    body: 'Make sure the server is running on this machine, then try again. Your files are still staged.',
  },
  payload_too_large: {
    title: 'That upload is too large',
    body: 'A scan accepts up to 50 files of at most 10 MB each. Remove some files and try again.',
  },
  too_many_files: {
    title: 'Too many files',
    body: 'A single scan accepts up to 50 files.',
  },
  insufficient_files: {
    title: 'None of the files could be read',
    body: 'Each file was rejected for the reason below. Replace them and run the scan again.',
  },
  scan_failed: {
    title: 'The scan didn’t finish',
    body: 'Something went wrong while comparing the documents. Trying again usually helps.',
  },
  not_found: {
    title: 'This report is no longer available',
    body: 'It may have been deleted, or it passed the 90-day retention period.',
  },
}

interface ErrorStateProps {
  message: string
  code?: string
  fileErrors?: FileError[]
  onRetry?: () => void
  onDismiss: () => void
}

export function ErrorState({ message, code, fileErrors, onRetry, onDismiss }: ErrorStateProps) {
  const copy = (code && COPY[code]) || { title: 'The scan failed', body: message }

  return (
    <div className="error-state" role="alert">
      <span className="error-state-icon" aria-hidden="true">
        <AlertIcon size={20} />
      </span>
      <h2 className="error-state-title">{copy.title}</h2>
      <p className="error-state-body">{copy.body}</p>
      {fileErrors && fileErrors.length > 0 && (
        <ul className="notice notice-danger notice-list">
          {fileErrors.map((e, i) => (
            <li key={`${e.file}-${i}`}>
              <strong className="truncate" title={e.file}>
                {e.file}
              </strong>
              <span>{e.error}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="error-state-actions">
        {onRetry && (
          <button type="button" className="btn btn-primary" onClick={onRetry}>
            <RefreshIcon />
            Try again
          </button>
        )}
        <button type="button" className="btn btn-secondary" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    </div>
  )
}
