import { useEffect, useState } from 'react';
import RiskBadge from './RiskBadge.jsx';
import { formatPercent } from '../lib/format.js';

// Slim bar that appears once the main score card has scrolled out of view, so the result stays visible.
export default function MiniScoreBar({ targetId, title, score, level }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = document.getElementById(targetId);
    if (!el || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver(([entry]) => {
      // Only after it left through the top (the user scrolled down), not before it has appeared.
      setVisible(!entry.isIntersecting && entry.boundingClientRect.top < 0);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [targetId]);

  return (
    <div className={`mini-score${visible ? ' is-visible' : ''}`} aria-hidden={!visible} data-print-hide>
      <span className="mini-score__title">{title}</span>
      <span className="mini-score__value">{formatPercent(score)}</span>
      <RiskBadge level={level} />
    </div>
  );
}
