import { useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { useDialogFocus } from '../hooks/useDialogFocus.js';
import { describeError } from '../lib/format.js';

function Dialog({ title, message, confirmLabel, tone, busy, error, onConfirm, onCancel }) {
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  // The safe choice (Cancel) gets focus first, so Enter never confirms by accident.
  useDialogFocus({ dialogRef, initialRef: cancelRef, onClose: busy ? () => {} : onCancel });

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <div
        className="modal modal--confirm"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
        ref={dialogRef}
      >
        <h2 id="confirm-title" className="modal__title">
          {title}
        </h2>
        <p id="confirm-message">{message}</p>
        {error && (
          <p className="inline-error" role="alert">
            {describeError(error)}
          </p>
        )}
        <div className="modal__actions">
          <button type="button" className="btn btn-secondary" ref={cancelRef} onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className={`btn ${tone === 'danger' ? 'btn-danger' : 'btn-primary'}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? (
              <>
                <Loader2 size={16} aria-hidden="true" className="spin" />
                Working...
              </>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Confirmation for consequential actions (delete, approve, reject). Mounted only while open, so
 * focus handling starts fresh each time. `busy` blocks duplicate confirms; `error` shows a failure
 * inside the dialog so the user can retry or cancel.
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  tone = 'primary',
  busy = false,
  error = null,
  onConfirm,
  onCancel,
}) {
  if (!open) return null;
  return (
    <Dialog
      title={title}
      message={message}
      confirmLabel={confirmLabel}
      tone={tone}
      busy={busy}
      error={error}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
