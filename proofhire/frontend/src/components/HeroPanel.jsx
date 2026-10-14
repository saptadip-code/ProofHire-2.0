import { useEffect, useState } from 'react';
import { Gauge, ListChecks, Quote, Repeat2, Sparkles } from 'lucide-react';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion.js';

// Static description of what a report contains. No example listing, scores or numbers.
const PARTS = [
  { icon: Gauge, title: 'Risk estimate', text: 'A score and level, with the thresholds shown.' },
  { icon: Quote, title: 'Evidence', text: 'What was observed in the listing and what the model derived.' },
  { icon: Sparkles, title: 'Explanation', text: 'Key concerns linked to the evidence behind them.' },
  { icon: ListChecks, title: 'Verification checklist', text: 'Concrete steps to check the employer yourself.' },
  { icon: Repeat2, title: 'Repeat patterns', text: 'Contacts or domains seen in other stored assessments.' },
];

export default function HeroPanel() {
  const reduced = usePrefersReducedMotion();
  const [active, setActive] = useState(0);

  // Highlights each part in turn. Off when the user prefers reduced motion.
  useEffect(() => {
    if (reduced) return undefined;
    const timer = setInterval(() => setActive((i) => (i + 1) % PARTS.length), 2400);
    return () => clearInterval(timer);
  }, [reduced]);

  return (
    <div className="scan card hero-panel" role="group" aria-label="What every report includes">
      <div className="scan__bar">
        <span className="scan__dot" aria-hidden="true" />
        <span className="scan__dot" aria-hidden="true" />
        <span className="scan__dot" aria-hidden="true" />
        <span className="scan__file">What every report includes</span>
      </div>
      <ul className="hero-panel__list">
        {PARTS.map((part, index) => (
          <li key={part.title} className={!reduced && index === active ? 'is-active' : undefined} style={{ '--d': `${300 + index * 120}ms` }}>
            <part.icon size={20} aria-hidden="true" />
            <span>
              <strong>{part.title}</strong>
              <span className="hero-panel__text">{part.text}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
