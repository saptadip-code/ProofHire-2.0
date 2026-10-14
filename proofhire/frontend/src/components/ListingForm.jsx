import { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import ErrorSummary from './ErrorSummary.jsx';
import FormField from './FormField.jsx';
import {
  APPLICATION_CHANNEL_OPTIONS,
  EMPLOYMENT_TYPE_OPTIONS,
  INTERVIEW_MODE_OPTIONS,
  PAY_PERIOD_OPTIONS,
  WORK_MODE_OPTIONS,
} from '../lib/constants.js';
import { FIELD_LABELS, FIELD_LIMITS, INITIAL_VALUES, toPayload, validateListing } from '../lib/validation.js';

// Controlled form with every Section 5.2 field. Sections: Basics, Pay, Contact, Process, Extra.
// `serverFields` is the `fields` array of a 422 error, mapped back onto the inputs.
export default function ListingForm({
  onSubmit,
  loading = false,
  initialValues,
  serverFields = [],
  submitDisabled = false,
  submitHint = null,
}) {
  const [values, setValues] = useState(() => ({ ...INITIAL_VALUES, ...initialValues }));
  const [touched, setTouched] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [serverErrors, setServerErrors] = useState({});
  const [attempt, setAttempt] = useState(0); // counts failed submit attempts, to move focus to the summary
  const summaryRef = useRef(null);

  useEffect(() => {
    const map = {};
    serverFields.forEach((f) => {
      if (f && f.field) map[f.field] = f.message;
    });
    setServerErrors(map);
  }, [serverFields]);

  const errors = useMemo(() => validateListing(values), [values]);

  // Everything the user needs to fix, in form order: client checks after a submit attempt plus server (422) errors.
  const summaryItems = useMemo(() => {
    const merged = { ...(submitted ? errors : {}), ...serverErrors };
    return Object.keys(FIELD_LABELS)
      .filter((field) => merged[field])
      .map((field) => ({ field, label: FIELD_LABELS[field], message: merged[field] }));
  }, [errors, serverErrors, submitted]);

  useEffect(() => {
    if (attempt > 0) summaryRef.current?.focus();
  }, [attempt]);

  const errorFor = (name) => ((submitted || touched[name]) && errors[name]) || serverErrors[name] || null;

  function handleChange(event) {
    const { name, value } = event.target;
    setValues((prev) => ({ ...prev, [name]: value }));
    if (serverErrors[name]) {
      setServerErrors((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
  }

  function bind(name, hint) {
    const error = errorFor(name);
    const describedBy = [hint ? `f-${name}-hint` : null, error ? `f-${name}-error` : null].filter(Boolean).join(' ');
    return {
      id: `f-${name}`,
      name,
      value: values[name],
      onChange: handleChange,
      onBlur: () => setTouched((prev) => ({ ...prev, [name]: true })),
      'aria-invalid': error ? 'true' : undefined,
      'aria-describedby': describedBy || undefined,
    };
  }

  // These helpers return elements (not components) so inputs keep focus between renders.
  const text = (name, label, { required = false, hint = null, help = null, type = 'text', inputMode, placeholder } = {}) => (
    <FormField id={`f-${name}`} label={label} required={required} hint={hint} help={help} error={errorFor(name)}>
      <input className="control" type={type} inputMode={inputMode} placeholder={placeholder} {...bind(name, hint)} />
    </FormField>
  );

  const area = (name, label, { required = false, hint = null, help = null, rows = 4 } = {}) => {
    const max = FIELD_LIMITS[name]?.max;
    return (
      <FormField
        id={`f-${name}`}
        label={label}
        required={required}
        hint={hint}
        help={help}
        error={errorFor(name)}
        counter={max ? `${values[name].trim().length}/${max}` : null}
      >
        <textarea className="control" rows={rows} {...bind(name, hint)} />
      </FormField>
    );
  };

  const select = (name, label, options, { hint = null, help = null } = {}) => (
    <FormField id={`f-${name}`} label={label} required hint={hint} help={help} error={errorFor(name)}>
      <select className="control" {...bind(name, hint)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </FormField>
  );

  function handleSubmit(event) {
    event.preventDefault();
    setSubmitted(true);
    if (Object.keys(errors).length > 0) {
      setAttempt((n) => n + 1); // focus moves to the error summary once it renders
      return;
    }
    if (loading) return; // never submit twice while a request is pending
    onSubmit(toPayload(values));
  }

  return (
    <form className="listing-form" onSubmit={handleSubmit} noValidate>
      <ErrorSummary items={summaryItems} ref={summaryRef} />
      <fieldset className="form-section">
        <legend>Basics</legend>
        {text('title', 'Job title', { required: true, placeholder: 'e.g. Marketing Intern' })}
        {text('company_name', 'Company name', { required: true })}
        {area('description', 'Listing description', {
          required: true,
          rows: 7,
          hint: 'Paste the full text of the listing as you saw it.',
          help: 'Keep the wording exactly as it appeared. Do not remove pressure or payment wording, because ProofHire looks for it.',
        })}
        {area('requirements', 'Requirements', { rows: 3 })}
        <div className="form-row">
          {text('location', 'Location')}
          {select('work_mode', 'Work mode', WORK_MODE_OPTIONS)}
          {select('employment_type', 'Employment type', EMPLOYMENT_TYPE_OPTIONS)}
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Pay</legend>
        <div className="form-row">
          {text('salary_min', 'Minimum pay', { inputMode: 'numeric', hint: 'Whole number, no commas.' })}
          {text('salary_max', 'Maximum pay', { inputMode: 'numeric' })}
          {select('pay_period', 'Pay period', PAY_PERIOD_OPTIONS)}
          {text('currency', 'Currency', { required: true, hint: '3-letter code, for example INR.' })}
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Contact</legend>
        <div className="form-row">
          {text('contact_email', 'Contact email', { type: 'email', inputMode: 'email' })}
          {text('contact_phone', 'Contact phone', { type: 'tel', inputMode: 'tel' })}
        </div>
        {text('company_website', 'Company website', {
          type: 'url',
          inputMode: 'url',
          placeholder: 'https://',
          hint: 'Must start with http:// or https://',
        })}
      </fieldset>

      <fieldset className="form-section">
        <legend>Process</legend>
        {select('application_channel', 'How are you asked to apply?', APPLICATION_CHANNEL_OPTIONS, {
          help: 'How the listing says you should apply. Choose "Not stated" if it does not say.',
        })}
      </fieldset>

      <fieldset className="form-section">
        <legend>Extra</legend>
        <div className="form-row">
          {text('upfront_fee_amount', 'Upfront fee requested (INR)', {
            required: true,
            inputMode: 'numeric',
            hint: 'Amount the applicant was asked to pay. Use 0 if none.',
            help: 'Include any registration, training, kit or security fee requested before you start. Enter 0 if nothing was requested.',
          })}
          {select('interview_mode', 'Interview mode', INTERVIEW_MODE_OPTIONS, {
            help: 'How the interview is held, if the listing mentions one.',
          })}
        </div>
      </fieldset>

      <div className="form-actions">
        <button type="submit" className="btn btn-primary btn-lg" disabled={loading || submitDisabled}>
          {loading ? (
            <>
              <Loader2 size={18} aria-hidden="true" className="spin" />
              Analysing...
            </>
          ) : (
            'Analyse listing'
          )}
        </button>
        {submitDisabled && submitHint && <p className="muted small">{submitHint}</p>}
        <p className="sr-only" aria-live="polite">
          {loading ? 'Analysing the listing, please wait.' : ''}
        </p>
      </div>
    </form>
  );
}
