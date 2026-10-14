import { useState } from 'react';
import { Check, X } from 'lucide-react';
import ConfirmDialog from './ConfirmDialog.jsx';
import FormField from './FormField.jsx';
import StatusBadge from './StatusBadge.jsx';
import { REPORT_TYPE_OPTIONS, labelFor } from '../lib/constants.js';
import { formatDate } from '../lib/format.js';

const NOTE_MAX = 500;

const ACTIONS = {
  approved: {
    title: 'Approve this report?',
    message: 'An approved report counts toward the public report count on that assessment.',
    confirmLabel: 'Approve report',
    tone: 'primary',
  },
  rejected: {
    title: 'Reject this report?',
    message: 'A rejected report will not be counted. You can add a note, but the decision cannot be changed afterwards.',
    confirmLabel: 'Reject report',
    tone: 'danger',
  },
};

// One report awaiting (or past) moderation. Approve and reject both ask for confirmation first.
// `onReview(id, { status, moderator_note })` returns a promise; a 409 means it was already reviewed.
export default function ReportReviewCard({ report, onReview }) {
  const [note, setNote] = useState('');
  const [action, setAction] = useState(null); // 'approved' | 'rejected' | null (dialog closed)
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [noteError, setNoteError] = useState(null);
  const pending = report.status === 'pending';
  const noteId = `note-${report.id}`;

  function ask(status) {
    if (note.length > NOTE_MAX) {
      setNoteError(`The note can be at most ${NOTE_MAX} characters.`);
      return;
    }
    setNoteError(null);
    setError(null);
    setAction(status);
  }

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onReview(report.id, { status: action, moderator_note: note.trim() || null });
      setAction(null);
    } catch (err) {
      setError(
        err?.code === 'conflict'
          ? { code: 'conflict', message: 'This report was already reviewed. Reload the list to see its status.' }
          : err,
      );
      setBusy(false);
    }
  }

  const copy = action ? ACTIONS[action] : ACTIONS.approved;

  return (
    <li className="card review-card">
      <div className="review-card__head">
        <strong>{labelFor(REPORT_TYPE_OPTIONS, report.report_type)}</strong>
        <StatusBadge status={report.status} />
      </div>
      <p className="muted small">
        Assessment #{report.assessment_id} · Submitted {formatDate(report.created_at)}
      </p>
      <blockquote className="evidence-quote">{report.description}</blockquote>

      {pending ? (
        <>
          <FormField id={noteId} label="Moderator note" error={noteError} counter={`${note.length}/${NOTE_MAX}`}>
            <textarea
              id={noteId}
              className="control"
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              aria-invalid={noteError ? 'true' : undefined}
              aria-describedby={noteError ? `${noteId}-error` : undefined}
            />
          </FormField>
          <div className="review-card__actions">
            <button type="button" className="btn btn-primary btn-sm" onClick={() => ask('approved')}>
              <Check size={14} aria-hidden="true" />
              Approve
            </button>
            <button type="button" className="btn btn-danger btn-sm" onClick={() => ask('rejected')}>
              <X size={14} aria-hidden="true" />
              Reject
            </button>
          </div>
        </>
      ) : (
        report.moderator_note && <p className="small">Moderator note: {report.moderator_note}</p>
      )}

      <ConfirmDialog
        open={action !== null}
        title={copy.title}
        message={copy.message}
        confirmLabel={copy.confirmLabel}
        tone={copy.tone}
        busy={busy}
        error={error}
        onConfirm={confirm}
        onCancel={() => {
          setAction(null);
          setError(null);
        }}
      />
    </li>
  );
}
