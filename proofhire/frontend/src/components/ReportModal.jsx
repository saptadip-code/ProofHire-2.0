import { useRef, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import FormField from './FormField.jsx';
import { createReport } from '../api/reports.js';
import { useDialogFocus } from '../hooks/useDialogFocus.js';
import { REPORT_TYPE_OPTIONS } from '../lib/constants.js';
import { describeError } from '../lib/format.js';

const MIN_LEN = 10;
const MAX_LEN = 1000;

function ReportDialog({ assessmentId, onClose, onSuccess }) {
  const dialogRef = useRef(null);
  const firstRef = useRef(null);
  const [reportType, setReportType] = useState(REPORT_TYPE_OPTIONS[0].value);
  const [description, setDescription] = useState('');
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState(null);

  // Focus the first field, trap Tab, close on Escape, lock scroll, restore focus on close.
  useDialogFocus({ dialogRef, initialRef: firstRef, onClose });

  const trimmed = description.trim();
  const lengthError =
    trimmed.length < MIN_LEN || trimmed.length > MAX_LEN
      ? `Describe what you saw in ${MIN_LEN} to ${MAX_LEN} characters.`
      : null;

  async function handleSubmit(event) {
    event.preventDefault();
    setTouched(true);
    setServerError(null);
    if (lengthError) return;
    setSubmitting(true);
    try {
      await createReport({
        assessment_id: Number(assessmentId),
        report_type: reportType,
        description: trimmed,
      });
      onSuccess('Thank you. Your report was submitted and is pending review.');
      onClose();
    } catch (error) {
      if (error && error.code === 'conflict') {
        setServerError('You already reported this.');
      } else if (error && error.code === 'validation_error' && error.fields?.[0]) {
        setServerError(`${error.fields[0].field}: ${error.fields[0].message}`);
      } else {
        setServerError(describeError(error));
      }
      setSubmitting(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="report-title" ref={dialogRef}>
        <div className="modal__head">
          <h2 id="report-title" className="modal__title">
            Report this listing
          </h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close report form">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <p className="muted small">
          Reports are reviewed by a moderator before they count. Only approved reports are shown as counts.
        </p>

        <form onSubmit={handleSubmit} noValidate>
          <FormField id="report-type" label="What is wrong?" required>
            <select
              id="report-type"
              className="control"
              ref={firstRef}
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
            >
              {REPORT_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </FormField>

          <FormField
            id="report-description"
            label="Describe what you saw"
            required
            error={touched ? lengthError : null}
            counter={`${trimmed.length}/${MAX_LEN}`}
          >
            <textarea
              id="report-description"
              className="control"
              rows={5}
              maxLength={MAX_LEN + 200}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onBlur={() => setTouched(true)}
              aria-invalid={touched && lengthError ? 'true' : undefined}
              aria-describedby={touched && lengthError ? 'report-description-error' : undefined}
            />
          </FormField>

          {serverError && (
            <p className="inline-error" role="alert">
              {serverError}
            </p>
          )}

          <div className="modal__actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 size={16} aria-hidden="true" className="spin" />
                  Submitting...
                </>
              ) : (
                'Submit report'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Mounted only while open, so its form state resets every time.
export default function ReportModal({ assessmentId, open, onClose, onSuccess }) {
  if (!open) return null;
  return <ReportDialog assessmentId={assessmentId} onClose={onClose} onSuccess={onSuccess} />;
}
