import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import EmptyState from './EmptyState.jsx';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion.js';
import { CHART_COLORS } from '../lib/constants.js';

// Horizontal bars of the evidence signals seen most often across stored assessments.
export default function TopEvidenceChart({ items }) {
  const reduced = usePrefersReducedMotion();
  const rows = Array.isArray(items) ? items.slice(0, 8) : [];

  return (
    <div className="card">
      <h2 className="card__title">Most common evidence signals</h2>
      {rows.length === 0 ? (
        <EmptyState title="No evidence counts yet" message="Counts appear once assessments are stored." />
      ) : (
        <div className="chart" role="img" aria-label={`Bar chart of the most common evidence signals: ${rows.map((r) => `${r.label} ${r.count}`).join(', ')}`}>
          <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 38)}>
            <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" allowDecimals={false} label={{ value: 'Times seen', position: 'insideBottom', offset: -12 }} />
              <YAxis type="category" dataKey="label" width={120} tick={{ fontSize: 12 }} tickFormatter={(v) => (String(v).length > 18 ? `${String(v).slice(0, 17)}…` : v)} />
              <Tooltip />
              <Bar dataKey="count" name="Times seen" fill={CHART_COLORS.teal} radius={[0, 4, 4, 0]} isAnimationActive={!reduced} animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
