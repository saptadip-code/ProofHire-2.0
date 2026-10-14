import { useEffect, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { LogOut, Menu, Moon, Search, ShieldCheck, Sun, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext.jsx';
import { useTheme } from '../hooks/useTheme.js';

const LINKS = [
  { to: '/', label: 'Home' },
  { to: '/assess', label: 'Assess' },
  { to: '/compare', label: 'Compare' },
  { to: '/saved', label: 'Saved' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/about', label: 'About' },
];

export default function Navbar({ onOpenPalette }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  // Add a shadow once the page has scrolled, so the bar reads as floating above the content.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // Close the mobile menu after navigating.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  function handleLogout() {
    logout();
    navigate('/');
  }

  const links = user?.role === 'admin' ? [...LINKS, { to: '/admin/reports', label: 'Reports' }] : LINKS;
  const nextTheme = theme === 'dark' ? 'light' : 'dark';

  return (
    <header className={`navbar${scrolled ? ' is-scrolled' : ''}`}>
      <div className="container navbar__inner">
        <Link to="/" className="brand">
          <ShieldCheck size={22} aria-hidden="true" />
          ProofHire
        </Link>

        <button
          type="button"
          className="icon-btn navbar__toggle"
          aria-expanded={open}
          aria-controls="primary-nav"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
        </button>

        <nav id="primary-nav" className={`navbar__nav${open ? ' is-open' : ''}`} aria-label="Primary">
          <ul className="navbar__links">
            {links.map((link) => (
              <li key={link.to}>
                <NavLink to={link.to} className={({ isActive }) => `navlink${isActive ? ' is-active' : ''}`}>
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>

          <div className="navbar__actions">
            {onOpenPalette && (
              <button type="button" className="btn btn-secondary btn-sm navbar__search" onClick={onOpenPalette} aria-label="Open command palette">
                <Search size={14} aria-hidden="true" />
                <span>Search</span>
                <kbd aria-hidden="true">Ctrl K</kbd>
              </button>
            )}
            <button
              type="button"
              className="icon-btn theme-toggle"
              onClick={toggle}
              aria-label={`Switch to ${nextTheme} theme`}
              title={`Switch to ${nextTheme} theme`}
            >
              {theme === 'dark' ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
            </button>
            {user ? (
              <>
                <span className="navbar__user">{user.display_name}</span>
                <button type="button" className="btn btn-secondary btn-sm" onClick={handleLogout}>
                  <LogOut size={14} aria-hidden="true" />
                  Sign out
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn btn-secondary btn-sm">
                  Sign in
                </Link>
                <Link to="/register" className="btn btn-primary btn-sm">
                  Register
                </Link>
              </>
            )}
          </div>
        </nav>
      </div>
    </header>
  );
}
