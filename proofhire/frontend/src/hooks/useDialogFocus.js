import { useEffect, useRef } from 'react';

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * Focus management shared by every modal dialog:
 *  - moves focus to `initialRef` (or the first control) when it opens
 *  - traps Tab / Shift+Tab inside `dialogRef`
 *  - closes on Escape
 *  - locks page scroll while open and restores focus to the opener on close
 * Mount it only while the dialog is open (the dialogs here render conditionally).
 */
export function useDialogFocus({ dialogRef, initialRef, onClose }) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement;
    const first = initialRef?.current || dialogRef.current?.querySelector(FOCUSABLE);
    first?.focus();
    document.body.style.overflow = 'hidden';

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        closeRef.current();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const nodes = [...dialogRef.current.querySelectorAll(FOCUSABLE)].filter((n) => !n.disabled);
      if (nodes.length === 0) return;
      const firstNode = nodes[0];
      const lastNode = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === firstNode) {
        event.preventDefault();
        lastNode.focus();
      } else if (!event.shiftKey && document.activeElement === lastNode) {
        event.preventDefault();
        firstNode.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = '';
      if (previous && previous.focus) previous.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
