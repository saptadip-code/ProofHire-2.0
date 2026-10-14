import { Link, Navigate, useLocation } from 'react-router-dom';
import { ShieldX } from 'lucide-react';
import { useAuth } from '../context/AuthContext.jsx';
import EmptyState from './EmptyState.jsx';
import Skeleton from './Skeleton.jsx';

// Redirects signed-out visitors to /login (remembering where they came from).
// With `role`, signed-in users without that role see a "no access" state.
export default function ProtectedRoute({ role = null, children }) {
  const { token, user, ready } = useAuth();
  const location = useLocation();

  if (!ready) {
    return (
      <div className="container page">
        <Skeleton lines={4} label="Checking your session" />
      </div>
    );
  }
  if (!token) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  if (role && user?.role !== role) {
    return (
      <div className="container page">
        <EmptyState
          icon={ShieldX}
          title="You do not have access to this page"
          message="This area is only available to administrators."
          action={
            <Link to="/" className="btn btn-secondary">
              Back to home
            </Link>
          }
        />
      </div>
    );
  }
  return children;
}
