import { Sparkles, FileText } from 'lucide-react';

// Summary, key concerns (each chip jumps to its evidence item) and "what to verify".
export default function ExplanationCard({ explanation, onSelectEvidence }) {
  if (!explanation) {
    return (
      <div className="card">
        <h2 className="card__title">Explanation</h2>
        <p className="muted">No explanation is available for this assessment.</p>
      </div>
    );
  }

  const isLlm = explanation.source === 'llm';
  const concerns = Array.isArray(explanation.key_concerns) ? explanation.key_concerns : [];
  const verify = Array.isArray(explanation.what_to_verify) ? explanation.what_to_verify : [];

  return (
    <div className="card">
      <div className="card__head">
        <h2 className="card__title">Explanation</h2>
        <span className={`source-badge${isLlm ? ' source-badge--llm' : ''}`}>
          {isLlm ? <Sparkles size={14} aria-hidden="true" /> : <FileText size={14} aria-hidden="true" />}
          {isLlm ? 'AI-written' : 'Auto-generated'}
        </span>
      </div>

      <p className="explanation__summary">{explanation.summary}</p>
      {isLlm && (
        <p className="muted small">The AI only words the evidence. The score and level come from the model.</p>
      )}

      {concerns.length > 0 && (
        <>
          <h3 className="card__subtitle">Key concerns</h3>
          <ul className="concern-list">
            {concerns.map((concern, index) => (
              <li key={`${concern.text}-${index}`} className="concern">
                <span>{concern.text}</span>
                <span className="concern__chips">
                  {(concern.evidence_ids || []).map((id) => (
                    <button
                      key={id}
                      type="button"
                      className="chip"
                      onClick={() => onSelectEvidence && onSelectEvidence(id)}
                      aria-label={`Show evidence ${id}`}
                    >
                      {id}
                    </button>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {verify.length > 0 && (
        <>
          <h3 className="card__subtitle">What to verify</h3>
          <ul className="bullet-list">
            {verify.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
