import { useScrollSpy } from '../hooks/useScrollSpy.js';
import { prefersReducedMotion } from '../hooks/usePrefersReducedMotion.js';

// Sticky "jump to" bar. The active link follows the scroll position (aria-current).
export default function ReportNav({ sections }) {
  const active = useScrollSpy(sections.map((s) => s.id));

  function jump(event, id) {
    const target = document.getElementById(id);
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' });
    target.focus({ preventScroll: true });
  }

  return (
    <nav className="report-nav" aria-label="Report sections">
      <ul className="report-nav__list">
        {sections.map((section) => (
          <li key={section.id}>
            <a
              href={`#${section.id}`}
              className={`report-nav__link${active === section.id ? ' is-active' : ''}`}
              aria-current={active === section.id ? 'true' : undefined}
              onClick={(event) => jump(event, section.id)}
            >
              {section.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
