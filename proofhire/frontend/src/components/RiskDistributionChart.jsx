import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import EmptyState from './EmptyState.jsx';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion.js';
import { CHART_COLORS, RISK_LABELS, RISK_LEVELS } from '../lib/constants.js';
import { formatCount } from '../lib/format.js';

// Donut of assessments by risk level. A text list under the chart repeats the numbers,
// so the information never depends on colour alone.
export default function RiskDistributionChart({ distribution }) {
  const reduced = usePrefersReducedMotion();
  const data = RISK_LEVELS.map((level) => ({
    level,
    name: RISK_LABELS[level],
    value: distribution?.[level] ?? 0,
  }));
  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className="card">
      <h2 className="card__title">Risk distribution</h2>
      {total === 0 ? (
        <EmptyState title="No assessments to chart yet" message="Run an assessment and it will appear here." />
      ) : (
        <>
          <div className="chart" role="img" aria-label={`Assessments by risk level: ${data.map((d) => `${d.name} ${d.value}`).join(', ')}`}>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2} isAnimationActive={!reduced} animationDuration={900}>
                  {data.map((d) => (
                    <Cell key={d.level} fill={CHART_COLORS[d.level]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="chart-numbers">
            {data.map((d) => (
              <li key={d.level}>
                {d.name}: <strong>{formatCount(d.value)}</strong>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
