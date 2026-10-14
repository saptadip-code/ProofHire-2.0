// Loading placeholder. aria-live announces loading to screen readers (Section C5).
export default function Skeleton({ lines = 3, height = 16, label = 'Loading', className = '' }) {
  return (
    <div className={`skeleton-group ${className}`.trim()} role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}…</span>
      {Array.from({ length: lines }, (_, index) => (
        <div
          key={index}
          className="skeleton"
          aria-hidden="true"
          style={{ height, width: lines > 1 && index === lines - 1 ? '60%' : '100%' }}
        />
      ))}
    </div>
  );
}
