import { useRef } from 'react';
import { X } from 'lucide-react';
import { useDialogFocus } from '../hooks/useDialogFocus.js';
import { SHORTCUTS } from '../lib/palette.js';

function Dialog({ onClose }) {
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  useDialogFocus({ dialogRef, initialRef: closeRef, onClose });
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="shortcuts-title" ref={dialogRef}>
        <div className="modal__head">
          <h2 id="shortcuts-title" className="modal__title">
            Keyboard shortcuts
          </h2>
          <button type="button" className="icon-btn" onClick={onClose} ref={closeRef} aria-label="Close shortcuts">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <ul className="shortcut-list">
          {SHORTCUTS.map((s, i) => (
            <li key={i}>
              <span>{s.text}</span>
              <span className="shortcut-keys">
                {s.keys.map((k, j) => (
                  <span key={j}>
                    {j > 0 && <span className="shortcut-then"> then </span>}
                    <kbd>{k}</kbd>
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ul>
        <p className="muted small">Shortcuts are off while you are typing in a field.</p>
      </div>
    </div>
  );
}

export default function ShortcutsDialog({ open, onClose }) {
  return open ? <Dialog onClose={onClose} /> : null;
}
