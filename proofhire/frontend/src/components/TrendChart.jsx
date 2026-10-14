import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import EmptyState from './EmptyState.jsx';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion.js';
import { CHART_COLORS } from '../lib/constants.js';
import { formatShortDate } from '../lib/format.js';

// Three series (high, medium, low). Each line also has its own dash pattern, so colour is not the only cue.
export default function TrendChart({ trends, days = 14 }) {
  const reduced = usePrefersReducedMotion();
  const rows = Array.isArray(trends) ? trends : [];
  const hasData = rows.some((r) => r.count > 0 || r.high > 0 || r.medium > 0 || r.low > 0);

  return (
    <div className="card">
      <h2 className="card__title">Assessments over time</h2>
      {!hasData ? (
        <EmptyState title="No trend data yet" message={`Assessments from the last ${days} days will appear here.`} />
      ) : (
        <div className="chart" role="img" aria-label="Line chart of assessments per day, split by risk level">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 24, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tickFormatter={formatShortDate} interval="preserveStartEnd" minTickGap={24} label={{ value: 'Date', position: 'insideBottom', offset: -12 }} />
              <YAxis allowDecimals={false} label={{ value: 'Assessments', angle: -90, position: 'insideLeft' }} />
              <Tooltip labelFormatter={formatShortDate} />
              <Legend verticalAlign="top" />
              <Line type="monotone" dataKey="high" name="High risk" stroke={CHART_COLORS.high} strokeWidth={2} dot={false} isAnimationActive={!reduced} animationDuration={1000} />
              <Line type="monotone" dataKey="medium" name="Medium risk" stroke={CHART_COLORS.medium} strokeWidth={2} strokeDasharray="6 3" dot={false} isAnimationActive={!reduced} animationDuration={1000} animationBegin={150} />
              <Line type="monotone" dataKey="low" name="Low risk" stroke={CHART_COLORS.low} strokeWidth={2} strokeDasharray="2 3" dot={false} isAnimationActive={!reduced} animationDuration={1000} animationBegin={300} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
