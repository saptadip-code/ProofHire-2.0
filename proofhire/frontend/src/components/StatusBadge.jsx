import { CircleCheck, CircleX, Clock } from 'lucide-react';
import { REPORT_STATUS_LABELS } from '../lib/constants.js';

const ICONS = { pending: Clock, approved: CircleCheck, rejected: CircleX };

// Report status as icon + text (never colour alone).
export default function StatusBadge({ status }) {
  const Icon = ICONS[status];
  return (
    <span className={`status-badge status-badge--${Icon ? status : 'unknown'}`}>
      {Icon && <Icon size={14} aria-hidden="true" />}
      {REPORT_STATUS_LABELS[status] || 'Unknown status'}
    </span>
  );
}
