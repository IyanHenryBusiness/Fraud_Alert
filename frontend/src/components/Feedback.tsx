type LoadingStateProps = { label?: string }

export function LoadingState({ label = "Loading alert data" }: LoadingStateProps) {
  return <div className="feedback loading-state" role="status"><span className="spinner" />{label}</div>
}

type ErrorMessageProps = { message: string; onRetry?: () => void }

export function ErrorMessage({ message, onRetry }: ErrorMessageProps) {
  return (
    <div className="feedback error-state" role="alert">
      <strong>Something needs attention</strong>
      <span>{message}</span>
      {onRetry ? <button className="button secondary" onClick={onRetry}>Retry</button> : null}
    </div>
  )
}
