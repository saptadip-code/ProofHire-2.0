import { useEffect, useMemo, useState } from 'react';
import EmptyState from './EmptyState.jsx';
import { describeError } from '../lib/format.js';

// Verification checklist with optimistic updates. `onToggle(item, nextDone)` must return a promise;
// if it rejects, the checkbox rolls back and an error message is shown.
export default function ChecklistPanel({ items, onToggle }) {
  const [local, setLocal] = useState(Array.isArray(items) ? items : []);
  const [pending, setPending] = useState(() => new Set());
  const [error, setError] = useState(null);

  useEffect(() => {
    setLocal(Array.isArray(items) ? items : []);
  }, [items]);

  const sorted = useMemo(() => [...local].sort((a, b) => a.priority - b.priority), [local]);
  const doneCount = local.filter((i) => i.done).length;
  const total = local.length;
  const percent = total === 0 ? 0 : Math.round((doneCount / total) * 100);

  const setDone = (id, done) => setLocal((list) => list.map((i) => (i.id === id ? { ...i, done } : i)));
  const setBusy = (id, busy) =>
    setPending((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });

  async function handleToggle(item) {
    const nextDone = !item.done;
    setError(null);
    setDone(item.id, nextDone); // optimistic
    setBusy(item.id, true);
    try {
      await onToggle(item, nextDone);
    } catch (err) {
      setDone(item.id, !nextDone); // rollback
      setError(describeError(err));
    } finally {
      setBusy(item.id, false);
    }
  }

  return (
    <div className="card">
      <h2 className="card__title">Verification checklist</h2>
      {total === 0 ? (
        <EmptyState title="No checklist items" message="This assessment did not include any verification steps." />
      ) : (
        <>
          <div className="progress">
            <div
              className="progress__track"
              role="progressbar"
              aria-label="Checklist progress"
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuenow={doneCount}
              aria-valuetext={`${doneCount} of ${total} steps done`}
            >
              <div className="progress__fill" style={{ width: `${percent}%` }} />
            </div>
            <span className="progress__text">
              {doneCount} of {total} done
            </span>
          </div>

          {error && (
            <p className="inline-error" role="alert">
              {error} Your change was not saved.
            </p>
          )}

          <ul className="checklist">
            {sorted.map((item) => (
              <li key={item.id} className="checklist__item">
                <label className="check">
                  <input
                    type="checkbox"
                    checked={Boolean(item.done)}
                    disabled={pending.has(item.id)}
                    onChange={() => handleToggle(item)}
                  />
                  <span className={item.done ? 'check__text is-done' : 'check__text'}>{item.text}</span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
