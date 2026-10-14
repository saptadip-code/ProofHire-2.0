import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CornerDownLeft, Search } from 'lucide-react';
import { listAssessments } from '../api/assessments.js';
import { useAuth } from '../context/AuthContext.jsx';
import { useDialogFocus } from '../hooks/useDialogFocus.js';
import { filterCommands } from '../lib/palette.js';

const PAGES = [
  { id: 'p-home', group: 'Pages', label: 'Home', to: '/' },
  { id: 'p-assess', group: 'Pages', label: 'Assess a listing', to: '/assess', keywords: 'new submit paste' },
  { id: 'p-compare', group: 'Pages', label: 'Compare two listings', to: '/compare' },
  { id: 'p-saved', group: 'Pages', label: 'Saved assessments', to: '/saved', keywords: 'history my' },
  { id: 'p-dash', group: 'Pages', label: 'Dashboard', to: '/dashboard', keywords: 'metrics charts' },
  { id: 'p-about', group: 'Pages', label: 'About and limitations', to: '/about', keywords: 'method' },
];

function PaletteDialog({ onClose, onToggleTheme, onShowShortcuts }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const dialogRef = useRef(null);
  const inputRef = useRef(null);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [saved, setSaved] = useState([]);

  useDialogFocus({ dialogRef, initialRef: inputRef, onClose });

  // Saved assessments are only fetched while the palette is open, and only for signed-in users.
  useEffect(() => {
    if (!user) return undefined;
    const controller = new AbortController();
    listAssessments({ limit: 20 }, { signal: controller.signal })
      .then((data) => setSaved(Array.isArray(data?.items) ? data.items : []))
      .catch(() => setSaved([]));
    return () => controller.abort();
  }, [user]);

  const commands = useMemo(() => {
    const list = [...PAGES];
    if (user?.role === 'admin') list.push({ id: 'p-admin', group: 'Pages', label: 'Review reports', to: '/admin/reports', keywords: 'admin moderation' });
    list.push({ id: 'a-theme', group: 'Actions', label: 'Toggle light or dark theme', action: 'theme', keywords: 'dark mode' });
    list.push({ id: 'a-keys', group: 'Actions', label: 'Show keyboard shortcuts', action: 'shortcuts', keywords: 'help keys' });
    saved.forEach((item) => {
      const id = item.id ?? item.assessment_id;
      const title = item.title ?? item.listing?.title ?? 'Untitled listing';
      list.push({ id: `s-${id}`, group: 'Saved assessments', label: `#${id} ${title}`, to: `/assessment/${id}`, keywords: item.company_name || '' });
    });
    const typed = query.trim();
    if (/^\d+$/.test(typed)) list.unshift({ id: 'open-id', group: 'Open', label: `Open assessment #${typed}`, to: `/assessment/${typed}` });
    return list;
  }, [user, saved, query]);

  const results = useMemo(() => filterCommands(commands, query), [commands, query]);
  const safeActive = Math.min(active, Math.max(0, results.length - 1));

  function run(cmd) {
    if (!cmd) return;
    onClose();
    if (cmd.to) navigate(cmd.to);
    else if (cmd.action === 'theme') onToggleTheme();
    else if (cmd.action === 'shortcuts') onShowShortcuts();
  }

  function onKeyDown(event) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((safeActive + 1) % Math.max(1, results.length));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((safeActive - 1 + results.length) % Math.max(1, results.length));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      run(results[safeActive]);
    }
  }

  useEffect(() => {
    document.getElementById(`cmd-${results[safeActive]?.id}`)?.scrollIntoView({ block: 'nearest' });
  }, [safeActive, results]);

  let lastGroup = null;
  return (
    <div className="modal-backdrop command-palette" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal command" role="dialog" aria-modal="true" aria-label="Command palette" ref={dialogRef}>
        <div className="command__search">
          <Search size={18} aria-hidden="true" />
          <input
            ref={inputRef}
            className="command__input"
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-list"
            aria-activedescendant={results[safeActive] ? `cmd-${results[safeActive].id}` : undefined}
            aria-label="Search pages and assessments"
            placeholder="Search pages, actions and saved assessments"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
          />
        </div>
        <ul id="command-list" className="command__list" role="listbox" aria-label="Results">
          {results.length === 0 && <li className="command__empty">Nothing matches "{query}".</li>}
          {results.map((cmd, index) => {
            const heading = cmd.group !== lastGroup ? cmd.group : null;
            lastGroup = cmd.group;
            return (
              <li key={cmd.id} role="presentation">
                {heading && <p className="command__group">{heading}</p>}
                <div
                  id={`cmd-${cmd.id}`}
                  role="option"
                  aria-selected={index === safeActive}
                  className={`command__item${index === safeActive ? ' is-active' : ''}`}
                  onMouseMove={() => setActive(index)}
                  onClick={() => run(cmd)}
                >
                  <span>{cmd.label}</span>
                  {index === safeActive && <CornerDownLeft size={14} aria-hidden="true" />}
                </div>
              </li>
            );
          })}
        </ul>
        <p className="command__foot muted small">Up and down to move, Enter to open, Esc to close.</p>
      </div>
    </div>
  );
}

export default function CommandPalette({ open, onClose, onToggleTheme, onShowShortcuts }) {
  if (!open) return null;
  return <PaletteDialog onClose={onClose} onToggleTheme={onToggleTheme} onShowShortcuts={onShowShortcuts} />;
}
