import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ListingForm from '../components/ListingForm.jsx';
import ErrorBanner from '../components/ErrorBanner.jsx';
import { createAssessment } from '../api/assessments.js';
import { useWake } from '../context/WakeContext.jsx';
import { INITIAL_VALUES } from '../lib/validation.js';

const NO_FIELDS = [];

export default function Assess() {
  const navigate = useNavigate();
  const wake = useWake();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const lastPayload = useRef(null);

  async function submit(payload) {
    lastPayload.current = payload;
    setLoading(true);
    setError(null);
    try {
      const result = await createAssessment(payload); // stores owner_token for anonymous callers
      navigate(`/assessment/${result.assessment_id}`);
    } catch (err) {
      setError(err);
      setLoading(false);
    }
  }

  const isValidation = error?.code === 'validation_error';
  const waking = wake.status === 'pending';

  return (
    <div className="container page page--narrow">
      <h1 className="page__title">Assess a listing</h1>
      <p className="muted">
        Paste the listing as you saw it. Do not enter your own ID numbers, passwords or bank details.
      </p>

      <aside className="card guide" aria-labelledby="guide-title">
        <h2 id="guide-title" className="card__title">
          What to paste
        </h2>
        <ul className="guide__list">
          <li>The full listing text exactly as you saw it, including any pressure or payment wording.</li>
          <li>The pay, any fee you were asked to pay, and how you were asked to apply.</li>
          <li>Any contact email, phone number or website the listing gave.</li>
        </ul>
        <p className="muted small">Leave out your own ID numbers, passwords and bank details.</p>
      </aside>

      {error && (
        <ErrorBanner
          error={error}
          title={isValidation ? 'Please fix the highlighted fields' : 'Could not assess this listing'}
          onRetry={isValidation ? undefined : () => lastPayload.current && submit(lastPayload.current)}
        />
      )}

      <ListingForm
        initialValues={INITIAL_VALUES}
        onSubmit={submit}
        loading={loading}
        serverFields={isValidation ? error.fields : NO_FIELDS}
        submitDisabled={waking}
        submitHint="Waiting for the server to wake up. The button turns on as soon as it responds."
      />
    </div>
  );
}
