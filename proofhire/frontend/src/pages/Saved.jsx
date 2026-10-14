import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, LayoutGrid, Rows3, Trash2 } from 'lucide-react';
import ConfirmDialog from '../components/ConfirmDialog.jsx';
import EmptyState from '../components/EmptyState.jsx';
import ErrorBanner from '../components/ErrorBanner.jsx';
import RiskBadge from '../components/RiskBadge.jsx';
import Skeleton from '../components/Skeleton.jsx';
import { deleteAssessment, listAssessments } from '../api/assessments.js';
import { useToast } from '../context/ToastContext.jsx';
import { useAsync } from '../hooks/useAsync.js';
import { RISK_LABELS, RISK_LEVELS } from '../lib/constants.js';
import { formatDate, formatPercent } from '../lib/format.js';
import { sortAssessments } from '../lib/report.js';

const LIMIT = 10;

const SORTS = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'level_desc', label: 'Highest risk level first' },
  { value: 'risk_desc', label: 'Highest score first' },
  { value: 'risk_asc', label: 'Lowest score first' },
];

// Totals per risk level for the filter chips. Any failure just hides the counts.
async function loadCounts(signal) {
  try {
    const levels = ['', ...RISK_LEVELS];
    const results = await Promise.all(levels.map((level) => listAssessments({ page: 1, limit: 1, riskLevel: level }, { signal })));
    const out = {};
    levels.forEach((level, i) => {
      const total = Number(results[i]?.total);
      if (Number.isFinite(total)) out[level || 'all'] = total;
    });
    return out;
  } catch (err) {
    if (err?.code === 'cancelled') throw err;
    return null;
  }
}

// The list item shape (`[summary]` in Section 5.4) is read defensively until Part B confirms it.
const itemId = (item) => item?.id ?? item?.assessment_id;
const itemTitle = (item) => item?.title ?? item?.listing?.title ?? 'Untitled listing';
const itemCompany = (item) => item?.company_name ?? item?.listing?.company_name ?? '';

function SavedRow({ item, onAskDelete }) {
  const id = itemId(item);
  return (
    <li className="card saved-item">
      <div className="saved-item__main">
        <h2 className="saved-item__title">{itemTitle(item)}</h2>
        <p className="muted">
          {itemCompany(item)}
          {itemCompany(item) ? ' · ' : ''}
          {formatDate(item.created_at)}
        </p>
      </div>
      <div className="saved-item__risk">
        <RiskBadge level={item.risk_level} />
        <span>{formatPercent(item.risk_score, 0)}</span>
      </div>
      <div className="saved-item__actions">
        <Link to={`/assessment/${encodeURIComponent(id)}`} className="btn btn-secondary btn-sm">
          Open
        </Link>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onAskDelete} aria-label={`Delete ${itemTitle(item)}`}>
          <Trash2 size={14} aria-hidden="true" />
          Delete
        </button>
      </div>
    </li>
  );
}

function SavedTable({ items, onAskDelete }) {
  return (
    <div className="card saved-table-wrap">
      <table className="saved-table">
        <caption className="sr-only">Your saved assessments</caption>
        <thead>
          <tr>
            <th scope="col">Listing</th>
            <th scope="col">Assessed</th>
            <th scope="col">Risk</th>
            <th scope="col">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={itemId(item)}>
              <th scope="row">
                {itemTitle(item)}
                {itemCompany(item) && <span className="muted saved-table__company">{itemCompany(item)}</span>}
              </th>
              <td>{formatDate(item.created_at)}</td>
              <td>
                <span className="saved-item__risk">
                  <RiskBadge level={item.risk_level} />
                  <span>{formatPercent(item.risk_score, 0)}</span>
                </span>
              </td>
              <td className="saved-table__actions">
                <Link to={`/assessment/${encodeURIComponent(itemId(item))}`} className="btn btn-secondary btn-sm">
                  Open
                </Link>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => onAskDelete(item)} aria-label={`Delete ${itemTitle(item)}`}>
                  <Trash2 size={14} aria-hidden="true" />
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Saved() {
  const [page, setPage] = useState(1);
  const [risk, setRisk] = useState('');
  const [sort, setSort] = useState('newest');
  const [view, setView] = useState('cards');
  const [countsKey, setCountsKey] = useState(0);
  const toast = useToast();
  const [target, setTarget] = useState(null); // the item awaiting delete confirmation
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const { data, error, loading, run } = useAsync(
    (signal) => listAssessments({ page, limit: LIMIT, riskLevel: risk }, { signal }),
    { deps: [page, risk] },
  );

  const counts = useAsync(loadCounts, { deps: [countsKey] });
  const rawItems = Array.isArray(data?.items) ? data.items : [];
  const items = useMemo(() => sortAssessments(rawItems, sort), [rawItems, sort]);
  const total = Number(data?.total) || 0;
  const pages = Math.max(1, Math.ceil(total / LIMIT));

  function changeFilter(level) {
    setRisk(level);
    setPage(1);
    setTarget(null);
  }

  function closeDialog() {
    if (deleting) return;
    setTarget(null);
    setDeleteError(null);
  }

  async function confirmDelete() {
    if (!target || deleting) return; // ignore double clicks while a request is pending
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAssessment(itemId(target));
      setTarget(null);
      toast.push('Assessment deleted.');
      setCountsKey((k) => k + 1);
      // If that was the only item on the last page, step back one page.
      if (items.length === 1 && page > 1) setPage(page - 1);
      else await run();
    } catch (err) {
      setDeleteError(err); // shown inside the dialog so the user can retry or cancel
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="container page">
      <header className="saved-head">
        <h1 className="page__title">Saved assessments</h1>
      </header>

      <div className="saved-toolbar">
        <div className="filter-group" role="group" aria-label="Filter by risk level">
          {[{ value: '', label: 'All' }, ...RISK_LEVELS.map((l) => ({ value: l, label: RISK_LABELS[l] }))].map((f) => {
            const count = counts.data ? counts.data[f.value || 'all'] : undefined;
            return (
              <button
                key={f.value || 'all'}
                type="button"
                className={`filter-chip${risk === f.value ? ' is-active' : ''}`}
                aria-pressed={risk === f.value}
                onClick={() => changeFilter(f.value)}
              >
                {f.label}
                {count !== undefined && <span className="filter-chip__count">{count}</span>}
              </button>
            );
          })}
        </div>
        <div className="saved-toolbar__right">
          <div>
            <label htmlFor="saved-sort" className="field__label">
              Sort this page
            </label>
            <select id="saved-sort" className="control" value={sort} onChange={(e) => setSort(e.target.value)}>
              {SORTS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="view-toggle" role="group" aria-label="Layout">
            <button type="button" className={`icon-btn${view === 'cards' ? ' is-active' : ''}`} aria-pressed={view === 'cards'} aria-label="Card layout" onClick={() => setView('cards')}>
              <LayoutGrid size={18} aria-hidden="true" />
            </button>
            <button type="button" className={`icon-btn view-toggle__table${view === 'table' ? ' is-active' : ''}`} aria-pressed={view === 'table'} aria-label="Table layout" onClick={() => setView('table')}>
              <Rows3 size={18} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="card">
          <Skeleton lines={6} label="Loading your saved assessments" />
        </div>
      ) : error ? (
        <ErrorBanner error={error} title="Could not load your saved assessments" onRetry={run} />
      ) : items.length === 0 ? (
        <EmptyState
          title={risk ? 'No assessments match this filter' : 'No saved assessments yet'}
          message={risk ? 'Try another risk level.' : 'Assessments you run while signed in are saved here.'}
          action={
            risk ? (
              <button type="button" className="btn btn-secondary" onClick={() => setRisk('')}>
                Clear filter
              </button>
            ) : (
              <Link to="/assess" className="btn btn-primary">
                Assess a listing
              </Link>
            )
          }
        />
      ) : (
        <>
          {view === 'table' ? (
            <div className="saved-table-only">
              <SavedTable
                items={items}
                onAskDelete={(item) => {
                  setDeleteError(null);
                  setTarget(item);
                }}
              />
            </div>
          ) : null}
          <ul className={`saved-list stagger${view === 'table' ? ' saved-list--hide-wide' : ''}`}>
            {items.map((item) => (
              <SavedRow
                key={itemId(item)}
                item={item}
                onAskDelete={() => {
                  setDeleteError(null);
                  setTarget(item);
                }}
              />
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

      <ConfirmDialog
        open={target !== null}
        title="Delete this assessment?"
        message={target ? `"${itemTitle(target)}" will be removed from your saved list. This cannot be undone.` : ''}
        confirmLabel="Delete assessment"
        tone="danger"
        busy={deleting}
        error={deleteError}
        onConfirm={confirmDelete}
        onCancel={closeDialog}
      />
    </div>
  );
}
