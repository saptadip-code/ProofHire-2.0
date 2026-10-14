import { useMemo } from 'react';
import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import { annotateText } from '../lib/report.js';

// The submitted listing text with each observed evidence phrase marked and numbered.
// A mark is a button: activating it jumps to that evidence item. The tag carries the id and an
// arrow, so the marks never rely on colour alone.
export default function AnnotatedListing({ text, evidence, activeId = null, onSelect }) {
  const { segments, unmatched } = useMemo(() => annotateText(text, evidence), [text, evidence]);
  const marked = segments.filter((s) => s.id).length;

  if (!text) return null;
  return (
    <div className="card annot">
      <h2 className="card__title">Listing with evidence marked</h2>
      <p className="muted small">
        {marked > 0
          ? 'Marked phrases are signals found in the text you submitted. Select one to see its evidence.'
          : 'No phrases from the text matched an observed signal.'}
      </p>
      <p className="annot__text">
        {segments.map((seg, index) => {
          if (!seg.id) return <span key={index}>{seg.text}</span>;
          const up = seg.direction === 'increases_risk';
          const Arrow = up ? ArrowUpRight : ArrowDownRight;
          return (
            <button
              key={index}
              type="button"
              id={`annot-mark-${seg.id}`}
              className={`annot__mark annot__mark--${up ? 'up' : 'down'}${activeId === seg.id ? ' is-active' : ''}`}
              aria-label={`${seg.text}. Signal ${seg.id}, ${up ? 'increases' : 'decreases'} risk. Show evidence.`}
              onClick={() => onSelect && onSelect(seg.id)}
            >
              {seg.text}
              <sup className="annot__tag" aria-hidden="true">
                {seg.id}
                <Arrow size={10} />
              </sup>
            </button>
          );
        })}
      </p>
      {unmatched.length > 0 && (
        <div className="annot__unmatched">
          <p className="small">
            <strong>Signals without a matching phrase in the text</strong> (they come from the other fields you entered):
          </p>
          <ul>
            {unmatched.map((e) => (
              <li key={e.id}>
                <button type="button" className="link-btn" onClick={() => onSelect && onSelect(e.id)}>
                  {e.id}
                </button>{' '}
                {e.label}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
