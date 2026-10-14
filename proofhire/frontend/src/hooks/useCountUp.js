import { useEffect, useRef, useState } from 'react';
import { prefersReducedMotion } from './usePrefersReducedMotion.js';

const easeOutCubic = (t) => 1 - (1 - t) ** 3;

/**
 * useCountUp(target, { duration, delay, active })
 * Animates from 0 to `target` (requestAnimationFrame). Returns the current number.
 * With reduced motion, a non-finite target, or active=false it returns the target immediately
 * (active=false means "not started yet" and returns 0 so the animation can begin later).
 */
export function useCountUp(target, { duration = 1100, delay = 0, active = true } = {}) {
  const valid = typeof target === 'number' && Number.isFinite(target);
  const instant = !valid || prefersReducedMotion();
  const [value, setValue] = useState(instant ? (valid ? target : 0) : 0);
  const frame = useRef(0);

  useEffect(() => {
    if (!valid) return undefined;
    if (prefersReducedMotion()) {
      setValue(target);
      return undefined;
    }
    if (!active) {
      setValue(0);
      return undefined;
    }
    let start = null;
    const timer = setTimeout(() => {
      const tick = (now) => {
        if (start === null) start = now;
        const progress = Math.min(1, (now - start) / duration);
        setValue(target * easeOutCubic(progress));
        if (progress < 1) frame.current = requestAnimationFrame(tick);
      };
      frame.current = requestAnimationFrame(tick);
    }, delay);
    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(frame.current);
    };
  }, [target, duration, delay, active, valid]);

  return value;
}
