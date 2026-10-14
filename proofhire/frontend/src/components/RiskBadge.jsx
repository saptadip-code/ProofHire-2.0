import { ShieldCheck, ShieldAlert, ShieldX } from 'lucide-react';
import { RISK_LABELS } from '../lib/constants.js';

const ICONS = { low: ShieldCheck, medium: ShieldAlert, high: ShieldX };

// Pill with icon AND text, so risk is never conveyed by colour alone.
export default function RiskBadge({ level }) {
  const Icon = ICONS[level];
  if (!Icon) {
    return <span className="risk-badge">Risk level unknown</span>;
  }
  return (
    <span className={`risk-badge risk-badge--${level}`}>
      <Icon size={16} aria-hidden="true" />
      {RISK_LABELS[level]}
    </span>
  );
}
