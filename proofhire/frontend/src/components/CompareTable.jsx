import { Check } from 'lucide-react';
import EmptyState from './EmptyState.jsx';
import { formatCell } from '../lib/format.js';

function Cell({ label, value, better }) {
  return (
    <td data-label={label} className={better ? 'is-better' : undefined}>
      <span>{formatCell(value)}</span>
      {better && (
        <span className="better-tag">
          <Check size={14} aria-hidden="true" />
          Better
        </span>
      )}
    </td>
  );
}

// Side-by-side signals. The better side gets a teal tint AND a "Better" label (never colour alone).
// On narrow screens each row stacks into a card (see .compare-table in components.css).
export default function CompareTable({ rows, a, b }) {
  const list = Array.isArray(rows) ? rows : [];
  if (list.length === 0) {
    return <EmptyState title="Nothing to compare" message="The comparison did not return any signals." />;
  }

  const labelA = a?.title || a?.listing?.title || 'Listing A';
  const labelB = b?.title || b?.listing?.title || 'Listing B';

  return (
    <div className="table-wrap compare-wrap">
      <table className="compare-table">
        <caption className="sr-only">Comparison of the two assessments, signal by signal</caption>
        <thead>
          <tr>
            <th scope="col">Signal</th>
            <th scope="col">A: {labelA}</th>
            <th scope="col">B: {labelB}</th>
          </tr>
        </thead>
        <tbody>
          {list.map((row, index) => (
            <tr key={`${row.signal}-${index}`}>
              <th scope="row" data-label="Signal">
                {row.signal}
              </th>
              <Cell label={`A: ${labelA}`} value={row.a} better={row.better === 'a'} />
              <Cell label={`B: ${labelB}`} value={row.b} better={row.better === 'b'} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
