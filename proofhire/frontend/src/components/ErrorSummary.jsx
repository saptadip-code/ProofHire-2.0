import { AlertTriangle } from 'lucide-react';

// Lists every field error at the top of a form. Focus moves here after a failed submit (WCAG 3.3.1),
// and each entry jumps to its field. The "Error:" text in each field message keeps it from relying on colour.
export default function ErrorSummary({ items, ref }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="error-summary" role="alert" tabIndex={-1} ref={ref} aria-labelledby="error-summary-title">
      <AlertTriangle size={20} aria-hidden="true" className="error-banner__icon" />
      <div>
        <h2 id="error-summary-title" className="error-summary__title">
          {items.length === 1 ? 'Fix 1 field to continue' : `Fix ${items.length} fields to continue`}
        </h2>
        <ul>
          {items.map((item) => (
            <li key={item.field}>
              <a
                href={`#f-${item.field}`}
                onClick={(event) => {
                  const el = document.getElementById(`f-${item.field}`);
                  if (!el) return;
                  event.preventDefault();
                  el.focus();
                  el.scrollIntoView({ block: 'center' });
                }}
              >
                {item.label}: {item.message}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
