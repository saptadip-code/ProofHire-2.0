import { useInView } from '../hooks/useInView.js';
import { useCountUp } from '../hooks/useCountUp.js';
import { DEFAULT_THRESHOLDS, RISK_LABELS } from '../lib/constants.js';
import { formatPercent } from '../lib/format.js';

const CX = 110;
const CY = 110;
const R = 88;
const STROKE = 16;
const SWEEP_MS = 1400;

// t in [0,1] maps left -> top -> right along the semi-circle.
function point(t, radius = R) {
  const angle = Math.PI * (1 - t);
  return [CX + radius * Math.cos(angle), CY - radius * Math.sin(angle)];
}

function arc(t1, t2) {
  const [x1, y1] = point(t1);
  const [x2, y2] = point(t2);
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

function clamp01(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

/**
 * Semi-circle gauge. The arcs draw in, the marker sweeps to the score and the number counts up
 * once the gauge is on screen. Colour is decoration only: the percentage and level text carry the
 * meaning, and the accessible label always states the final values.
 * Props: `delay` (ms before the animation starts), `compact` (hides the threshold caption).
 */
export default function RiskGauge({ score, level, thresholds = DEFAULT_THRESHOLDS, delay = 0, compact = false }) {
  const [ref, inView] = useInView({ threshold: 0.3 });
  const value = clamp01(score);
  const low = clamp01(thresholds?.low ?? DEFAULT_THRESHOLDS.low);
  const high = clamp01(thresholds?.high ?? DEFAULT_THRESHOLDS.high);

  const shown = useCountUp(value, { duration: SWEEP_MS, delay: delay + 500, active: inView });
  const [mx, my] = point(shown);
  const levelLabel = RISK_LABELS[level] || 'Risk level unknown';
  const description = `Risk score ${formatPercent(value)}. ${levelLabel}. Level thresholds at ${formatPercent(low)} and ${formatPercent(high)}.`;

  const ticks = [low, high].map((t) => {
    const [x1, y1] = point(t, R - STROKE / 2 - 3);
    const [x2, y2] = point(t, R + STROKE / 2 + 3);
    const [lx, ly] = point(t, R + STROKE / 2 + 15);
    return { t, x1, y1, x2, y2, lx, ly };
  });

  const segments = [
    { key: 'low', d: arc(0, low), start: 0 },
    { key: 'medium', d: arc(low, high), start: 200 },
    { key: 'high', d: arc(high, 1), start: 400 },
  ];

  return (
    <figure className={`gauge${inView ? ' is-drawn' : ''}`} ref={ref} style={{ '--gd': `${delay}ms` }}>
      <svg viewBox="0 0 220 138" role="img" aria-label={description} className="gauge__svg">
        {segments.map((seg) => (
          <path
            key={seg.key}
            d={seg.d}
            pathLength="1"
            className={`gauge__segment gauge__segment--${seg.key}`}
            strokeWidth={STROKE}
            fill="none"
            style={{ '--sd': `${seg.start}ms` }}
          />
        ))}

        {ticks.map((tick) => (
          <g key={tick.t} className="gauge__ticks">
            <line x1={tick.x1} y1={tick.y1} x2={tick.x2} y2={tick.y2} className="gauge__tick" />
            <text x={tick.lx} y={tick.ly} textAnchor="middle" className="gauge__tick-label">
              {formatPercent(tick.t)}
            </text>
          </g>
        ))}

        <circle cx={mx} cy={my} r={9} className="gauge__marker" />

        <text x={CX} y={CY - 12} textAnchor="middle" className="gauge__value">
          {formatPercent(shown)}
        </text>
        <text x={CX} y={CY + 10} textAnchor="middle" className="gauge__level">
          {levelLabel}
        </text>
      </svg>
      {!compact && (
        <figcaption className="gauge__caption">
          Level thresholds: {formatPercent(low)} and {formatPercent(high)}
        </figcaption>
      )}
    </figure>
  );
}
