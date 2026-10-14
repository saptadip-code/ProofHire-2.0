import AnimatedNumber from './AnimatedNumber.jsx';
import Sparkline from './Sparkline.jsx';

// A single headline number. Pass `number` for a count-up (missing values show a dash), or `value`
// for text that is already formatted.
export default function KpiCard({ label, number, value = null, hint = null, icon: Icon = null, trend = null, trendLabel = '' }) {
  return (
    <div className="card card--lift kpi-card">
      <div className="kpi-card__label">
        {Icon && <Icon size={16} aria-hidden="true" />}
        <span>{label}</span>
      </div>
      <p className="kpi-card__value">{number !== undefined ? <AnimatedNumber value={number} /> : value}</p>
      {trend && trend.length > 1 && <Sparkline values={trend} label={trendLabel || label} />}
      {hint && <p className="kpi-card__hint">{hint}</p>}
    </div>
  );
}
