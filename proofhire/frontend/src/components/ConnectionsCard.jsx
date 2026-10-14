import { Link2, ShieldAlert } from 'lucide-react';
import EmptyState from './EmptyState.jsx';
import { SIGNAL_TYPE_LABELS } from '../lib/constants.js';
import { pluralize } from '../lib/format.js';

// Repeat-pattern connections: the same masked email/phone/domain seen in other stored assessments.
export default function ConnectionsCard({ connections }) {
  const list = Array.isArray(connections) ? connections : [];
  return (
    <div className="card">
      <h2 className="card__title">Repeat patterns</h2>
      {list.length === 0 ? (
        <EmptyState
          icon={Link2}
          title="No repeat patterns found in stored assessments"
          message="None of this listing's contact details or domains appear in other stored assessments."
        />
      ) : (
        <ul className="connection-list">
          {list.map((c, index) => {
            const flagged = Number(c.high_risk_count) > 0;
            return (
              <li key={`${c.signal_type}-${c.value_masked}-${index}`} className="connection">
                <div>
                  <span className="connection__type">{SIGNAL_TYPE_LABELS[c.signal_type] || c.signal_type}</span>
                  <span className="connection__value">{c.value_masked}</span>
                </div>
                <div className={`connection__seen${flagged ? ' is-flagged' : ''}`}>
                  Seen {c.times_seen} {pluralize(Number(c.times_seen), 'time')}
                  {flagged && (
                    <span className="connection__flag">
                      <ShieldAlert size={14} aria-hidden="true" />
                      {c.high_risk_count} high-risk
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
