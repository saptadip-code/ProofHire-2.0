import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import ErrorBanner from '../components/ErrorBanner.jsx';
import FormField from '../components/FormField.jsx';
import { useAuth } from '../context/AuthContext.jsx';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function Login() {
  const { user, login, sessionExpired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from;
  const destination = from ? `${from.pathname}${from.search || ''}` : '/';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (user) return <Navigate to={destination} replace />;

  const emailError = submitted && !EMAIL_RE.test(email.trim()) ? 'Enter a valid email address.' : null;
  const passwordError = submitted && !password ? 'Enter your password.' : null;

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitted(true);
    setError(null);
    if (!EMAIL_RE.test(email.trim()) || !password) return;
    setLoading(true);
    try {
      await login({ email: email.trim(), password });
      navigate(destination, { replace: true });
    } catch (err) {
      setError(err);
      setLoading(false);
    }
  }

  return (
    <div className="container page page--auth">
      <div className="card">
        <h1 className="page__title">Sign in</h1>
        <p className="muted">Sign in to keep a saved list of your assessments. You can also assess listings without an account.</p>
        {sessionExpired && !error && (
          <p className="notice notice--warn" role="status">
            Your session has ended, so you were signed out. Please sign in again to continue.
          </p>
        )}
        {error && <ErrorBanner error={error} title="Could not sign in" />}
        <form onSubmit={handleSubmit} noValidate>
          <FormField id="login-email" label="Email" required error={emailError}>
            <input
              id="login-email"
              className="control"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={emailError ? 'true' : undefined}
              aria-describedby={emailError ? 'login-email-error' : undefined}
            />
          </FormField>
          <FormField id="login-password" label="Password" required error={passwordError}>
            <input
              id="login-password"
              className="control"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={passwordError ? 'true' : undefined}
              aria-describedby={passwordError ? 'login-password-error' : undefined}
            />
          </FormField>
          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? (
              <>
                <Loader2 size={16} aria-hidden="true" className="spin" />
                Signing in...
              </>
            ) : (
              'Sign in'
            )}
          </button>
        </form>
        <p className="muted small">
          New here?{' '}
          <Link to="/register" state={location.state}>
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
