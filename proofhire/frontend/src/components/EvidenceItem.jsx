import { useState } from 'react';
import { ArrowUpRight, ArrowDownRight, ChevronDown, Search } from 'lucide-react';
import { explainEvidence } from '../lib/insights.js';

function SeverityDots({ severity }) {
  const level = Math.min(3, Math.max(0, Number(severity) || 0));
  return (
    <span className="severity" role="img" aria-label={`Severity ${level} of 3`}>
      {[1, 2, 3].map((n) => (
        <span key={n} className={`severity__dot${n <= level ? ' is-on' : ''}`} aria-hidden="true" />
      ))}
    </span>
  );
}

// One evidence signal. `maxWeight` scales the model weight bar. The element id lets key-concern
// chips scroll to it (`evidence-E1`). "Why this counts" expands to show how the signal was derived.
export default function EvidenceItem({ item, highlighted = false, maxWeight = 1, onShowInListing }) {
  const [open, setOpen] = useState(false);
  const increases = item.direction === 'increases_risk';
  const DirectionIcon = increases ? ArrowUpRight : ArrowDownRight;
  const hasWeight = item.type === 'model' && typeof item.weight === 'number';
  const barPercent = hasWeight && maxWeight > 0 ? Math.min(100, (Math.abs(item.weight) / maxWeight) * 100) : 0;
  const detailsId = `evidence-${item.id}-details`;
  const rows = explainEvidence(item);

  return (
    <li
      id={`evidence-${item.id}`}
      tabIndex={-1}
      className={`evidence-item evidence-item--${increases ? 'up' : 'down'}${highlighted ? ' is-highlighted' : ''}`}
    >
      <div className="evidence-item__head">
        <span className="evidence-item__id">{item.id}</span>
        <span className="evidence-item__direction">
          <DirectionIcon size={16} aria-hidden="true" />
          {increases ? 'Increases risk' : 'Decreases risk'}
        </span>
        <SeverityDots severity={item.severity} />
      </div>
      <p className="evidence-item__label">{item.label}</p>
      {item.snippet && <blockquote className="evidence-quote">{item.snippet}</blockquote>}
      {hasWeight && (
        <div className="weight">
          <div className="weight__bar" aria-hidden="true">
            <span className="weight__fill" style={{ width: `${barPercent}%` }} />
          </div>
          <span className="weight__text">Model weight {item.weight.toFixed(2)}</span>
        </div>
      )}

      {onShowInListing && item.type === 'observed' && item.snippet && (
        <button type="button" className="evidence-item__toggle" onClick={() => onShowInListing(item.id)}>
          <Search size={16} aria-hidden="true" />
          Show in listing
          <span className="sr-only"> for signal {item.id}</span>
        </button>
      )}
      <button
        type="button"
        className="evidence-item__toggle"
        aria-expanded={open}
        aria-controls={detailsId}
        onClick={() => setOpen((v) => !v)}
      >
        <ChevronDown size={16} aria-hidden="true" className="evidence-item__chevron" />
        {open ? 'Hide why this counts' : 'Why this counts'}
        <span className="sr-only"> for signal {item.id}</span>
      </button>
      {open && (
        <div id={detailsId} className="evidence-item__details">
          <dl className="why-list">
            {rows.map((row) => (
              <div key={row.term} className="why-list__row">
                <dt>{row.term}</dt>
                <dd>{row.text}</dd>
              </div>
            ))}
          </dl>
          <p className="muted small">This is a risk signal, not proof about the employer.</p>
        </div>
      )}
    </li>
  );
}
