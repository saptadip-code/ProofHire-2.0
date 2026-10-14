import { Database, FlaskConical } from 'lucide-react';

// States plainly where the usage numbers come from, so demo rows are never mistaken for real use.
export default function DataSourceBadge({ includeDemo }) {
  const Icon = includeDemo ? FlaskConical : Database;
  return (
    <p className="data-source" role="status">
      <Icon size={16} aria-hidden="true" />
      <span>
        <strong>Data source: </strong>
        {includeDemo
          ? 'live stored assessments plus seeded synthetic demo rows.'
          : 'live stored assessments only.'}
      </span>
    </p>
  );
}
