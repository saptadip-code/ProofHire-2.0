import { Info } from 'lucide-react';
import { boundaryNote, levelGuidance } from '../lib/insights.js';

// Plain-language meaning of the level, with a note when the score sits close to a threshold.
// Wording is deliberately a prompt to verify, never a verdict about the employer.
export default function ScoreContext({ level, score, thresholds }) {
  const boundary = boundaryNote(score, thresholds);
  return (
    <div className="score-context" role="note">
      <Info size={16} aria-hidden="true" />
      <div>
        <p>{levelGuidance(level)}</p>
        {boundary && <p>{boundary}</p>}
        <p className="muted small">The score is a model estimate based only on the details submitted.</p>
      </div>
    </div>
  );
}
