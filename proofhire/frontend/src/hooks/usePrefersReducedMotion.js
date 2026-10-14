import { useEffect, useState } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';

export function prefersReducedMotion() {
  return typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia(QUERY).matches;
}

// Reactive version: updates if the user flips the OS setting while the app is open.
export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(prefersReducedMotion);

  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const media = window.matchMedia(QUERY);
    const onChange = () => setReduced(media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  return reduced;
}
