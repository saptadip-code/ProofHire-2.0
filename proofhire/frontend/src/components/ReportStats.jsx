import { ArrowDownRight, ArrowUpRight, Gauge, ListChecks } from 'lucide-react';
import AnimatedNumber from './AnimatedNumber.jsx';

function Stat({ icon: Icon, label, children, hint }) {
  return (
    <li className="card report-stat">
      <span className="report-stat__label">
        <Icon size={16} aria-hidden="true" />
        {label}
      </span>
      <span className="report-stat__value">{children}</span>
      {hint && <span className="report-stat__hint">{hint}</span>}
    </li>
  );
}

// Four headline numbers for a report. Counts come straight from the assessment data.
export default function ReportStats({ data }) {
  const evidence = Array.isArray(data.evidence) ? data.evidence : [];
  const up = evidence.filter((e) => e.direction === 'increases_risk').length;
  const down = evidence.length - up;
  const steps = Array.isArray(data.checklist) ? data.checklist.length : 0;
  const score = typeof data.risk_score === 'number' ? data.risk_score * 100 : null;

  return (
    <ul className="report-stats stagger">
      <Stat icon={Gauge} label="Risk score" hint={data.risk_level ? 'Model estimate' : null}>
        <AnimatedNumber value={score} format={(n) => `${n.toFixed(0)}%`} />
      </Stat>
      <Stat icon={ArrowUpRight} label="Increase risk" hint="Evidence signals">
        <AnimatedNumber value={up} />
      </Stat>
      <Stat icon={ArrowDownRight} label="Decrease risk" hint="Evidence signals">
        <AnimatedNumber value={down} />
      </Stat>
      <Stat icon={ListChecks} label="Checklist" hint="Steps to verify">
        <AnimatedNumber value={steps} />
      </Stat>
    </ul>
  );
}
