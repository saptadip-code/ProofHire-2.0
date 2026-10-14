import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import EmptyState from '../components/EmptyState.jsx';
import ErrorBanner from '../components/ErrorBanner.jsx';
import ReportReviewCard from '../components/ReportReviewCard.jsx';
import Skeleton from '../components/Skeleton.jsx';
import { useToast } from '../context/ToastContext.jsx';
import { listAdminReports, reviewReport } from '../api/reports.js';
import { useAsync } from '../hooks/useAsync.js';
import { REPORT_STATUS_LABELS } from '../lib/constants.js';

const LIMIT = 20;
const STATUSES = ['pending', 'approved', 'rejected'];

export default function AdminReports() {
  const toast = useToast();
  const [status, setStatus] = useState('pending');
  const [page, setPage] = useState(1);

  const { data, error, loading, run } = useAsync((signal) => listAdminReports({ status, page, limit: LIMIT }, { signal }), {
    deps: [status, page],
  });

  const items = Array.isArray(data?.items) ? data.items : [];
  const total = Number(data?.total) || 0;
  const pages = Math.max(1, Math.ceil(total / LIMIT));

  async function handleReview(id, body) {
    await reviewReport(id, body);
    toast.push(`Report ${body.status}.`);
    // If that emptied the page, step back; otherwise reload the list.
    if (items.length === 1 && page > 1) setPage(page - 1);
    else await run();
  }

  return (
    <div className="container page page--narrow">
      <header className="saved-head">
        <h1 className="page__title">Report moderation</h1>
        <div>
          <label htmlFor="status-filter" className="field__label">
            Status
          </label>
          <select
            id="status-filter"
            className="control"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {REPORT_STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
      </header>

      {loading ? (
        <div className="card">
          <Skeleton lines={6} label="Loading reports" />
        </div>
      ) : error ? (
        <ErrorBanner error={error} title="Could not load reports" onRetry={run} />
      ) : items.length === 0 ? (
        <EmptyState
          title={status === 'pending' ? 'No reports are waiting for review' : `No ${status} reports`}
          message="Reports submitted by users will appear here."
        />
      ) : (
        <>
          <ul className="review-list stagger">
            {items.map((report) => (
              <ReportReviewCard key={report.id} report={report} onReview={handleReview} />
            ))}
          </ul>
          <nav className="pagination" aria-label="Pagination">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPage((p) => p - 1)} disabled={page <= 1}>
              <ChevronLeft size={14} aria-hidden="true" />
              Previous
            </button>
            <span aria-live="polite">
              Page {page} of {pages}
            </span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPage((p) => p + 1)} disabled={page >= pages}>
              Next
              <ChevronRight size={14} aria-hidden="true" />
            </button>
          </nav>
        </>
      )}
    </div>
  );
}
