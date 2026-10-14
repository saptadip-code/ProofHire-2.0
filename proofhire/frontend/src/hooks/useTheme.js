import { useCallback, useEffect, useState } from 'react';
import { storage } from '../api/client.js';
import { STORAGE_KEYS } from '../lib/constants.js';

const THEME_EVENT = 'ph:theme';
const current = () => document.documentElement.getAttribute('data-theme') || 'light';

// Light/dark theme stored in ph_theme. index.html applies the saved value before first paint.
// Every component that uses this hook stays in sync, whoever toggles (navbar or command palette).
export function useTheme() {
  const [theme, setTheme] = useState(current);

  useEffect(() => {
    const sync = () => setTheme(current());
    window.addEventListener(THEME_EVENT, sync);
    return () => window.removeEventListener(THEME_EVENT, sync);
  }, []);

  const toggle = useCallback(() => {
    const next = current() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    storage.set(STORAGE_KEYS.theme, next);
    window.dispatchEvent(new Event(THEME_EVENT));
  }, []);

  return { theme, toggle };
}
