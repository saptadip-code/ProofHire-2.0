import { useEffect, useId, useRef, useState } from 'react';
import { CircleHelp } from 'lucide-react';

// Click-to-reveal help (works with keyboard and touch, unlike hover-only tooltips).
// The text stays in the page flow, so it never clips off-screen at 360 px. Escape or an outside click closes it.
export default function HelpTip({ label, children }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const id = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const onPointer = (event) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [open]);

  return (
    <span className="helptip" ref={wrapRef}>
      <button
        type="button"
        className="helptip__button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`Help: ${label}`}
        onClick={() => setOpen((v) => !v)}
      >
        <CircleHelp size={16} aria-hidden="true" />
      </button>
      {open && (
        <span id={id} role="note" className="helptip__text">
          {children}
        </span>
      )}
    </span>
  );
}
