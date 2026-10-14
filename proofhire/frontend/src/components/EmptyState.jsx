import { Inbox } from 'lucide-react';

// Empty state for any list/chart with no data.
export default function EmptyState({ title, message, action = null, icon: Icon = Inbox }) {
  return (
    <div className="empty-state">
      <Icon size={28} aria-hidden="true" className="empty-state__icon" />
      <p className="empty-state__title">{title}</p>
      {message && <p className="empty-state__text">{message}</p>}
      {action}
    </div>
  );
}
