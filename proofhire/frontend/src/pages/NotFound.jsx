import { Link } from 'react-router-dom';
import { SearchX } from 'lucide-react';
import EmptyState from '../components/EmptyState.jsx';

export default function NotFound() {
  return (
    <div className="container page">
      <EmptyState
        icon={SearchX}
        title="Page not found"
        message="The page you are looking for does not exist."
        action={
          <Link to="/" className="btn btn-primary">
            Back to home
          </Link>
        }
      />
    </div>
  );
}
