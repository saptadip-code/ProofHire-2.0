import { sparklinePoints } from '../lib/report.js';

// Tiny trend line for a KPI card. Decorative: the number and `label` carry the meaning.
export default function Sparkline({ values, label, width = 96, height = 28 }) {
  const points = sparklinePoints(values, width, height);
  if (!points) return null;
  const nums = values.map(Number).filter(Number.isFinite);
  const total = nums.reduce((a, b) => a + b, 0);
  return (
    <figure className="sparkline">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label}: ${total} in total over ${nums.length} days`}>
        <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <figcaption className="sr-only">{label}</figcaption>
    </figure>
  );
}
