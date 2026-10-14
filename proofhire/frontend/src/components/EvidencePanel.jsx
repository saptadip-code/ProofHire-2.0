import { useEffect, useMemo, useState } from 'react';
import EvidenceItem from './EvidenceItem.jsx';
import EmptyState from './EmptyState.jsx';
import { prefersReducedMotion } from '../hooks/usePrefersReducedMotion.js';

const FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'increases_risk', label: 'Increases risk' },
  { value: 'decreases_risk', label: 'Decreases risk' },
];

// Increasing-risk items first; the order the ML pipeline returned is preserved inside each group.
function orderItems(items) {
  const up = items.filter((i) => i.direction === 'increases_risk');
  const down = items.filter((i) => i.direction !== 'increases_risk');
  return [...up, ...down];
}

function EvidenceGroup({ title, description, items, highlightId, maxWeight, emptyText, onShowInListing }) {
  return (
    <section className="evidence-group" aria-label={title}>
      <h3 className="evidence-group__title">
        {title} <span className="count-pill">{items.length}</span>
      </h3>
      <p className="evidence-group__desc">{description}</p>
      {items.length === 0 ? (
        <p className="muted">{emptyText}</p>
      ) : (
        <ul className="evidence-list stagger">
          {items.map((item) => (
            <EvidenceItem key={item.id} item={item} highlighted={item.id === highlightId} maxWeight={maxWeight} onShowInListing={onShowInListing} />
          ))}
        </ul>
      )}
    </section>
  );
}

// Two groups: what was OBSERVED in the submitted listing vs. patterns DERIVED by the model.
// A filter narrows both groups by direction; the list re-keys on filter change so it animates in again.
export default function EvidencePanel({ evidence, highlightId = null, highlightNonce = 0, onShowInListing }) {
  const list = Array.isArray(evidence) ? evidence : [];
  const [filter, setFilter] = useState('all');

  const counts = useMemo(
    () => ({
      all: list.length,
      increases_risk: list.filter((i) => i.direction === 'increases_risk').length,
      decreases_risk: list.filter((i) => i.direction !== 'increases_risk').length,
    }),
    [list],
  );

  const { observed, model, maxWeight } = useMemo(() => {
    const keep = (i) => filter === 'all' || (filter === 'increases_risk') === (i.direction === 'increases_risk');
    const obs = orderItems(list.filter((i) => i.type === 'observed' && keep(i)));
    const mod = orderItems(list.filter((i) => i.type === 'model' && keep(i)));
    const weights = list.filter((i) => i.type === 'model').map((i) => (typeof i.weight === 'number' ? Math.abs(i.weight) : 0));
    return { observed: obs, model: mod, maxWeight: Math.max(0, ...weights) || 1 };
  }, [list, filter]);

  // A key-concern chip must always be able to reach its item, so it clears the filter first,
  // then scrolls to and focuses that item.
  useEffect(() => {
    if (!highlightId) return undefined;
    setFilter('all');
    const timer = setTimeout(() => {
      const el = document.getElementById(`evidence-${highlightId}`);
      if (!el) return;
      el.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'center' });
      el.focus({ preventScroll: true });
    }, 80);
    return () => clearTimeout(timer);
  }, [highlightId, highlightNonce]);

  if (list.length === 0) {
    return (
      <div className="card">
        <h2 className="card__title">Evidence</h2>
        <EmptyState
          title="No evidence signals were returned"
          message="The assessment did not produce any evidence items for this listing."
        />
      </div>
    );
  }

  return (
    <div className="card" id="evidence-panel">
      <div className="card__head">
        <h2 className="card__title">Evidence</h2>
        <div className="filter-group" role="group" aria-label="Filter evidence by effect on risk">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              className={`filter-chip${filter === f.value ? ' is-active' : ''}`}
              aria-pressed={filter === f.value}
              onClick={() => setFilter(f.value)}
            >
              {f.label} <span className="filter-chip__count">{counts[f.value]}</span>
            </button>
          ))}
        </div>
      </div>
      <p className="sr-only" aria-live="polite">
        Showing {observed.length + model.length} of {list.length} evidence signals.
      </p>
      <div className="evidence-grid" key={filter}>
        <EvidenceGroup
          title="Observed in the listing"
          description="User-provided: found directly in the text and details you submitted. ProofHire has not verified them."
          items={observed}
          highlightId={highlightId}
          maxWeight={maxWeight}
          onShowInListing={onShowInListing}
          emptyText="No signals from your listing match this filter."
        />
        <EvidenceGroup
          title="Model-derived patterns"
          description="Model inference: statistical patterns learned from synthetic training data. They are not facts about the employer."
          items={model}
          highlightId={highlightId}
          maxWeight={maxWeight}
          emptyText="No model-derived patterns match this filter."
        />
      </div>
    </div>
  );
}
