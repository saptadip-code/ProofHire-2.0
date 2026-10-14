import { Loader2, AlertTriangle, RefreshCw } from 'lucide-react';

// Shown while the free-tier server wakes up (Section C1) and when retries are exhausted.
export default function WakeBanner({ status, attempts, maxAttempts, onRetry }) {
  if (status === 'unreachable') {
    return (
      <div className="wake-banner wake-banner--error" role="alert">
        <AlertTriangle size={18} aria-hidden="true" />
        <span>
          We could not reach the server after {maxAttempts} attempts. You can still try, or check again.
        </span>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
          <RefreshCw size={14} aria-hidden="true" />
          Check again
        </button>
      </div>
    );
  }
  return (
    <div className="wake-banner" role="status" aria-live="polite">
      <Loader2 size={18} aria-hidden="true" className="spin" />
      <span>
        Server is waking up, this can take up to a minute. (Attempt {Math.max(attempts, 1)} of {maxAttempts})
      </span>
    </div>
  );
}
