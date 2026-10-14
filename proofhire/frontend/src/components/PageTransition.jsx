import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

// Re-keys its wrapper on every route change so the CSS enter animation replays, resets scroll,
// and moves focus to <main> so keyboard and screen-reader users start at the top of the new page.
export default function PageTransition({ children }) {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
    const main = document.getElementById('main');
    if (main) main.focus({ preventScroll: true });
  }, [pathname]);

  return (
    <div key={pathname} className="page-transition">
      {children}
    </div>
  );
}
