import { useEffect, useState } from 'react';

/**
 * useScrollSpy(ids) -> id of the section currently nearest the top of the viewport.
 * Uses IntersectionObserver with a band just below the sticky headers. Returns the first id
 * until something intersects, and always works without IntersectionObserver (stays on the first id).
 */
export function useScrollSpy(ids) {
  const [active, setActive] = useState(ids[0] ?? null);
  const key = ids.join('|');

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return undefined;
    const nodes = ids.map((id) => document.getElementById(id)).filter(Boolean);
    if (nodes.length === 0) return undefined;

    const visible = new Set();
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) visible.add(entry.target.id);
          else visible.delete(entry.target.id);
        });
        const first = ids.find((id) => visible.has(id));
        if (first) setActive(first);
      },
      { rootMargin: '-120px 0px -55% 0px', threshold: 0 },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return active;
}
