import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { GitCompare } from 'lucide-react';
import CompareTable from '../components/CompareTable.jsx';
import EmptyState from '../components/EmptyState.jsx';
import ErrorBanner from '../components/ErrorBanner.jsx';
import RiskBadge from '../components/RiskBadge.jsx';
import Skeleton from '../components/Skeleton.jsx';
import { compareAssessments, listAssessments } from '../api/assessments.js';
import { useAuth } from '../context/AuthContext.jsx';
import { useAsync } from '../hooks/useAsync.js';
import { formatPercent } from '../lib/format.js';

const REAL_ID = /^\d+$/;

function checkId(value) {
  const v = value.trim();
  if (!v) return 'Enter an assessment id.';
  if (!REAL_ID.test(v)) return 'Use the assessment number, for example 42.';
  return null;
}

function runComparison(a, b, signal) {
  return compareAssessments(Number(a), Number(b), { signal });
}

function itemId(item) {
  return item?.id ?? item?.assessment_id;
}
function itemTitle(item) {
  return item?.title ?? item?.listing?.title ?? 'Untitled listing';
}

function SideCard({ label, result, fallbackId }) {
  // POST /assessments/compare returns AssessmentSummary objects: { id, title, company_name, risk_score, risk_level, ... }
  const id = itemId(result) ?? fallbackId;
  return (
    <div className="card compare-side">
      <p className="eyebrow">{label}</p>
      <h3 className="compare-side__title">{result ? itemTitle(result) : `Assessment ${fallbackId}`}</h3>
      <p className="muted">{result?.company_name ?? result?.listing?.company_name}</p>
      {result?.risk_level && (
        <p className="compare-side__risk">
          <RiskBadge level={result.risk_level} />
          <span>{formatPercent(result.risk_score, 1)}</span>
        </p>
      )}
      <Link to={`/assessment/${encodeURIComponent(id)}`} className="btn btn-secondary btn-sm">
        Open report
      </Link>
    </div>
  );
}

function SidePicker({ label, value, onChange, error, saved }) {
  const inputId = `compare-${label}`;
  return (
    <div className="card">
      <label htmlFor={inputId} className="field__label">
        Assessment {label.toUpperCase()}
      </label>
      <input
        id={inputId}
        className="control"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Assessment id, e.g. 42"
        inputMode="text"
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={error ? `${inputId}-error` : undefined}
      />
      {error && (
        <p className="field__error" id={`${inputId}-error`} role="alert">
          {error}
        </p>
      )}
      {saved.length > 0 && (
        <>
          <label htmlFor={`${inputId}-saved`} className="field__label field__label--spaced">
            Or choose from your saved assessments
          </label>
          <select
            id={`${inputId}-saved`}
            className="control"
            value=""
            onChange={(e) => e.target.value && onChange(e.target.value)}
          >
            <option value="">Choose…</option>
            {saved.map((item) => (
              <option key={itemId(item)} value={String(itemId(item))}>
                #{itemId(item)} · {itemTitle(item)}
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  );
}

export default function Compare() {
  const [params, setParams] = useSearchParams();
  const { user } = useAuth();
  const [idA, setIdA] = useState(params.get('a') || '');
  const [idB, setIdB] = useState(params.get('b') || '');
  const [errors, setErrors] = useState({});
  const [started, setStarted] = useState(false);

  const comparison = useAsync((signal, a, b) => runComparison(a, b, signal), { immediate: false });
  const savedCall = useAsync((signal) => listAssessments({ limit: 50 }, { signal }), { immediate: Boolean(user), deps: [user?.id] });
  const saved = Array.isArray(savedCall.data?.items) ? savedCall.data.items : [];

  function submit(a, b) {
    const next = { a: checkId(a), b: checkId(b) };
    if (!next.a && !next.b && a.trim() === b.trim()) next.b = 'Choose two different assessments.';
    setErrors(next);
    if (next.a || next.b) return;
    setStarted(true);
    setParams({ a: a.trim(), b: b.trim() }, { replace: true });
    comparison.run(a.trim(), b.trim());
  }

  // Deep link such as /compare?a=1&b=2 runs once on load.
  useEffect(() => {
    const a = params.get('a');
    const b = params.get('b');
    if (a && b) submit(a, b);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const result = comparison.data;

  return (
    <div className="container page">
      <h1 className="page__title">Compare two listings</h1>
      <p className="muted">
        Put two assessments side by side. Enter ids from your report pages, or choose from your saved assessments.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(idA, idB);
        }}
        noValidate
      >
        <div className="compare-pickers">
          <SidePicker label="a" value={idA} onChange={setIdA} error={errors.a} saved={saved} />
          <SidePicker label="b" value={idB} onChange={setIdB} error={errors.b} saved={saved} />
        </div>
        {savedCall.error && (
          <ErrorBanner error={savedCall.error} title="Could not load your saved assessments" onRetry={savedCall.run} />
        )}
        <button type="submit" className="btn btn-primary" disabled={comparison.loading}>
          <GitCompare size={16} aria-hidden="true" />
          {comparison.loading ? 'Comparing...' : 'Compare'}
        </button>
      </form>

      <section className="section" aria-live="polite">
        {comparison.loading ? (
          <div className="card">
            <Skeleton lines={6} label="Comparing assessments" />
          </div>
        ) : comparison.error ? (
          <ErrorBanner
            error={comparison.error}
            title="Could not compare these assessments"
            onRetry={() => submit(idA, idB)}
          />
        ) : result ? (
          <>
            <div className="compare-sides">
              <SideCard label="Listing A" result={result.a} fallbackId={idA.trim()} />
              <SideCard label="Listing B" result={result.b} fallbackId={idB.trim()} />
            </div>
            <CompareTable rows={result.rows} a={result.a} b={result.b} />
          </>
        ) : (
          !started && (
            <EmptyState
              icon={GitCompare}
              title="Choose two assessments to compare"
              message="Enter two assessment ids from your report pages, or pick from your saved assessments if you are signed in."
            />
          )
        )}
      </section>
    </div>
  );
}
