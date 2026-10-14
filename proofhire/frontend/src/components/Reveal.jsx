import { useInView } from '../hooks/useInView.js';

/**
 * Fades and lifts its children into view once they scroll on screen.
 * `delay` (ms) staggers siblings. Content is always in the DOM, so screen readers and
 * reduced-motion users are unaffected (the CSS disables the transform when reduced motion is on).
 */
export default function Reveal({ as: Tag = 'div', delay = 0, className = '', children, ...rest }) {
  const [ref, inView] = useInView();
  return (
    <Tag
      ref={ref}
      className={`reveal${inView ? ' is-visible' : ''} ${className}`.trim()}
      style={{ '--reveal-delay': `${delay}ms` }}
      {...rest}
    >
      {children}
    </Tag>
  );
}
