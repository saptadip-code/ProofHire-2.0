import { useMemo } from 'react';
import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import { scoreDrivers } from '../lib/report.js';

function Group({ title, note, rows }) {
  if (rows.length === 0) return null;
  return (
    <section className="drivers__group" aria-label={title}>
      <h3 className="drivers__title">{title}</h3>
      <p className="muted small">{note}</p>
      <ul className="drivers__list">
        {rows.map((row) => {
          const Arrow = row.increases ? ArrowUpRight : ArrowDownRight;
          return (
            <li key={row.id} className="drivers__row">
              <span className="drivers__label">
                <strong>{row.id}</strong> {row.label}
              </span>
              <span className="drivers__meta">
                <Arrow size={14} aria-hidden="true" />
                {row.increases ? 'Increases risk' : 'Decreases risk'} · {row.text}
              </span>
              <span className="drivers__track" aria-hidden="true">
                <span
                  className={`drivers__bar drivers__bar--${row.increases ? 'up' : 'down'}`}
                  style={{ width: `${Math.max(4, Math.round(row.size * 100))}%` }}
                />
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// What moved the estimate. Observed signals are sized by severity and model signals by weight.
// The two use different scales, so they are shown as two separate groups.
export default function ScoreDrivers({ evidence }) {
  const { observed, model } = useMemo(() => scoreDrivers(evidence), [evidence]);
  if (observed.length === 0 && model.length === 0) return null;
  return (
    <div className="card drivers">
      <h2 className="card__title">What moved the estimate</h2>
      <div className="drivers__grid">
        <Group title="Observed in the listing" note="Bar length shows severity from 1 to 3." rows={observed} />
        <Group title="Model-derived patterns" note="Bar length shows weight relative to the largest model weight." rows={model} />
      </div>
    </div>
  );
}
