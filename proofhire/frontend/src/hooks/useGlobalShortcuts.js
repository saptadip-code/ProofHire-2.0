import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { GO_KEYS, isTypingTarget } from '../lib/palette.js';

/** Ctrl/Cmd+K or "/" opens the palette, "?" opens help, "g" then a letter navigates. */
export function useGlobalShortcuts({ openPalette, openHelp, enabled }) {
  const navigate = useNavigate();
  const pendingG = useRef(0);

  useEffect(() => {
    function onKeyDown(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (!document.querySelector('[aria-modal="true"]')) openPalette();
        return;
      }
      if (!enabled || document.querySelector('[aria-modal="true"]') || event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target)) return;

      if (event.key === '/') {
        event.preventDefault();
        openPalette();
      } else if (event.key === '?') {
        event.preventDefault();
        openHelp();
      } else if (event.key.toLowerCase() === 'g') {
        pendingG.current = Date.now();
      } else if (Date.now() - pendingG.current < 1200 && GO_KEYS[event.key.toLowerCase()]) {
        pendingG.current = 0;
        navigate(GO_KEYS[event.key.toLowerCase()].to);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [navigate, openPalette, openHelp, enabled]);
}
