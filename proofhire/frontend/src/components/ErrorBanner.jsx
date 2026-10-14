import { AlertTriangle, RefreshCw } from 'lucide-react';
import { describeError } from '../lib/format.js';

// Error state with a working Retry. `error` can be an ApiError, an Error or a string.
export default function ErrorBanner({ error, onRetry, title = 'Something went wrong' }) {
  if (!error) return null;
  return (
    <div className="error-banner" role="alert">
      <AlertTriangle size={20} aria-hidden="true" className="error-banner__icon" />
      <div className="error-banner__body">
        <strong>{title}</strong>
        <p>{describeError(error)}</p>
      </div>
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          <RefreshCw size={16} aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  );
}
