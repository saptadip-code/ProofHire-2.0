import { useMemo, useState } from 'react';
import { BarChart3, FlaskConical, Flag, ShieldX } from 'lucide-react';
import DataSourceBadge from '../components/DataSourceBadge.jsx';
import KpiCard from '../components/KpiCard.jsx';
import MetricsCard from '../components/MetricsCard.jsx';
import ConfusionMatrix from '../components/ConfusionMatrix.jsx';
import RiskDistributionChart from '../components/RiskDistributionChart.jsx';
import TrendChart from '../components/TrendChart.jsx';
import TopEvidenceChart from '../components/TopEvidenceChart.jsx';
import ErrorBanner from '../components/ErrorBanner.jsx';
import EmptyState from '../components/EmptyState.jsx';
import Skeleton from '../components/Skeleton.jsx';
import {
  getModelMetrics,
  getSummary,
  getTrends,
  normalizeMetrics,
  normalizeSummary,
  normalizeTrends,
} from '../api/dashboard.js';
import { useAsync } from '../hooks/useAsync.js';
import { METRICS_BADGE } from '../lib/constants.js';

function SectionState({ loading, error, onRetry, skeletonLines = 4, children }) {
  if (loading) {
    return (
      <div className="card">
        <Skeleton lines={skeletonLines} label="Loading" />
      </div>
    );
  }
  if (error) return <ErrorBanner error={error} onRetry={onRetry} title="Could not load this section" />;
  return children;
}

const RANGES = [7, 14, 30];

export default function Dashboard() {
  // Default is REAL stored data only. The toggle adds seeded synthetic demo rows (is_synthetic_demo).
  const [includeDemo, setIncludeDemo] = useState(false);
  const [days, setDays] = useState(14);

  const summaryCall = useAsync((signal) => getSummary(includeDemo, { signal }), { deps: [includeDemo] });
  const trendsCall = useAsync((signal) => getTrends(includeDemo, days, { signal }), { deps: [includeDemo, days] });
  const metricsCall = useAsync((signal) => getModelMetrics({ signal }));

  const summary = useMemo(() => normalizeSummary(summaryCall.data), [summaryCall.data]);
  const trends = useMemo(() => normalizeTrends(trendsCall.data), [trendsCall.data]);
  const metrics = useMemo(() => normalizeMetrics(metricsCall.data), [metricsCall.data]);

  return (
    <div className="container page">
      <header className="dashboard-head">
        <div>
          <h1 className="page__title">Dashboard</h1>
          <p className="source-badge">
            <FlaskConical size={14} aria-hidden="true" />
            {METRICS_BADGE}
          </p>
        </div>
        <label className="toggle">
          <input type="checkbox" checked={includeDemo} onChange={(e) => setIncludeDemo(e.target.checked)} />
          <span>
            Include seeded demo data
            <span className="toggle__hint">
              {includeDemo ? 'Showing real and synthetic demo rows.' : 'Showing real stored data only.'}
            </span>
          </span>
        </label>
      </header>

      <section aria-labelledby="usage-title" className="section">
        <h2 id="usage-title" className="section__title">
          Usage
        </h2>
        <DataSourceBadge includeDemo={includeDemo} />
        <SectionState loading={summaryCall.loading} error={summaryCall.error} onRetry={summaryCall.run}>
          {!summary ? (
            <EmptyState title="No summary available" message="The server returned no usage summary." />
          ) : (
            <>
              <div className="kpi-grid stagger">
                <KpiCard
                  label="Assessments stored"
                  number={summary.totalAssessments}
                  icon={BarChart3}
                  trend={trends.map((t) => t.count)}
                  trendLabel={`Assessments per day, last ${days} days`}
                />
                <KpiCard
                  label="High-risk assessments"
                  number={summary.highRiskCount}
                  icon={ShieldX}
                  trend={trends.map((t) => t.high)}
                  trendLabel={`High-risk assessments per day, last ${days} days`}
                />
                <KpiCard
                  label="Approved reports"
                  number={summary.reportsApproved}
                  hint="Only moderator-approved reports count."
                  icon={Flag}
                />
                <KpiCard label="Reports awaiting review" number={summary.reportsPending} icon={Flag} />
              </div>
              <div className="chart-grid stagger">
                <RiskDistributionChart distribution={summary.distribution} />
                <TopEvidenceChart items={summary.topEvidence} />
              </div>
            </>
          )}
        </SectionState>

        <SectionState loading={trendsCall.loading} error={trendsCall.error} onRetry={trendsCall.run} skeletonLines={6}>
          <div className="range-picker" role="group" aria-label="Trend date range">
            {RANGES.map((n) => (
              <button key={n} type="button" className={`filter-chip${days === n ? ' is-active' : ''}`} aria-pressed={days === n} onClick={() => setDays(n)}>
                Last {n} days
              </button>
            ))}
          </div>
          <TrendChart trends={trends} days={days} />
        </SectionState>
      </section>

      <section aria-labelledby="model-title" className="section">
        <h2 id="model-title" className="section__title">
          Model evaluation
        </h2>
        <SectionState loading={metricsCall.loading} error={metricsCall.error} onRetry={metricsCall.run} skeletonLines={5}>
          <div className="chart-grid stagger">
            <MetricsCard metrics={metrics} />
            <div className="card">
              <h2 className="card__title">Confusion matrix</h2>
              <ConfusionMatrix matrix={metrics?.confusion ?? null} />
            </div>
          </div>
        </SectionState>
      </section>
    </div>
  );
}
