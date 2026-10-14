import { Link } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';
import { DISCLAIMER } from '../lib/constants.js';

const PRODUCT_LINKS = [
  { to: '/assess', label: 'Assess a listing' },
  { to: '/compare', label: 'Compare listings' },
  { to: '/dashboard', label: 'Dashboard' },
];
const LEARN_LINKS = [
  { to: '/about', label: 'How it works and its limits' },
];

// The disclaimer is required copy on every page (Section C5).
export default function Footer() {
  return (
    <footer className="footer">
      <div className="container footer__grid">
        <div className="footer__brand">
          <p className="brand brand--footer">
            <ShieldCheck size={20} aria-hidden="true" />
            ProofHire
          </p>
          <p className="footer__disclaimer">{DISCLAIMER}</p>
          <p className="footer__meta">ProofHire is a hackathon prototype built on synthetic data.</p>
        </div>
        <nav aria-label="Product" className="footer__col">
          <p className="footer__heading">Product</p>
          <ul>
            {PRODUCT_LINKS.map((link) => (
              <li key={link.to}>
                <Link to={link.to}>{link.label}</Link>
              </li>
            ))}
          </ul>
        </nav>
        <nav aria-label="Learn" className="footer__col">
          <p className="footer__heading">Learn</p>
          <ul>
            {LEARN_LINKS.map((link) => (
              <li key={link.to}>
                <Link to={link.to}>{link.label}</Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}
