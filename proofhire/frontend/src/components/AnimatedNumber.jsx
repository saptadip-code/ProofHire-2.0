import { useInView } from '../hooks/useInView.js';
import { useCountUp } from '../hooks/useCountUp.js';

/**
 * Counts up when scrolled into view. `format(n)` turns the number into display text.
 * Screen readers get the FINAL value once (visually hidden text); the animated digits are
 * aria-hidden, so assistive tech never reads intermediate numbers.
 */
export default function AnimatedNumber({ value, format = (n) => Math.round(n).toLocaleString('en-IN'), duration, delay }) {
  const [ref, inView] = useInView({ threshold: 0.4 });
  const current = useCountUp(value, { duration, delay, active: inView });
  const valid = typeof value === 'number' && Number.isFinite(value);
  return (
    <span ref={ref}>
      <span className="sr-only">{valid ? format(value) : 'Not available'}</span>
      <span aria-hidden="true">{valid ? format(current) : '—'}</span>
    </span>
  );
}
