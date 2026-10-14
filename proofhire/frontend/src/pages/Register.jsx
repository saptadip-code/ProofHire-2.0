import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import ErrorBanner from '../components/ErrorBanner.jsx';
import FormField from '../components/FormField.jsx';
import { useAuth } from '../context/AuthContext.jsx';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function validate({ displayName, email, password }) {
  const errors = {};
  const name = displayName.trim();
  if (name.length < 1 || name.length > 100) errors.display_name = 'Enter a name of 1 to 100 characters.';
  if (!EMAIL_RE.test(email.trim()) || email.trim().length > 255) errors.email = 'Enter a valid email address.';
  if (password.length < 8 || password.length > 72) errors.password = 'Use 8 to 72 characters.';
  return errors;
}

export default function Register() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from;
  const destination = from ? `${from.pathname}${from.search || ''}` : '/';

  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (user) return <Navigate to={destination} replace />;

  const clientErrors = submitted ? validate({ displayName, email, password }) : {};
  // Server `fields` errors (422) are mapped back onto the inputs.
  const serverErrors = {};
  if (error?.code === 'validation_error') {
    error.fields.forEach((f) => {
      if (f.field) serverErrors[f.field] = f.message;
    });
  }
  const errorFor = (name) => clientErrors[name] || serverErrors[name] || null;

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitted(true);
    setError(null);
    if (Object.keys(validate({ displayName, email, password })).length > 0) return;
    setLoading(true);
    try {
      await register({ email: email.trim(), password, display_name: displayName.trim() });
      navigate(destination, { replace: true });
    } catch (err) {
      setError(err);
      setLoading(false);
    }
  }

  const describe = (name) => (errorFor(name) ? `register-${name}-error` : undefined);

  return (
    <div className="container page page--auth">
      <div className="card">
        <h1 className="page__title">Create an account</h1>
        <p className="muted">An account lets you keep a saved list of your assessments.</p>
        {error && <ErrorBanner error={error} title="Could not create the account" />}
        <form onSubmit={handleSubmit} noValidate>
          <FormField id="register-display_name" label="Display name" required error={errorFor('display_name')}>
            <input
              id="register-display_name"
              className="control"
              autoComplete="name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              aria-invalid={errorFor('display_name') ? 'true' : undefined}
              aria-describedby={describe('display_name')}
            />
          </FormField>
          <FormField id="register-email" label="Email" required error={errorFor('email')}>
            <input
              id="register-email"
              className="control"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={errorFor('email') ? 'true' : undefined}
              aria-describedby={describe('email')}
            />
          </FormField>
          <FormField
            id="register-password"
            label="Password"
            required
            hint="8 to 72 characters."
            error={errorFor('password')}
          >
            <input
              id="register-password"
              className="control"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={errorFor('password') ? 'true' : undefined}
              aria-describedby={['register-password-hint', describe('password')].filter(Boolean).join(' ')}
            />
          </FormField>
          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? (
              <>
                <Loader2 size={16} aria-hidden="true" className="spin" />
                Creating account...
              </>
            ) : (
              'Create account'
            )}
          </button>
        </form>
        <p className="muted small">
          Already registered?{' '}
          <Link to="/login" state={location.state}>
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
