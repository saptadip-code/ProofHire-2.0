// Pure helpers for the command palette and keyboard shortcuts.

/** Keeps commands whose label or keywords contain every word typed. Empty query keeps all. */
export function filterCommands(commands, query) {
  const words = String(query || '').toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return commands;
  return commands.filter((c) => {
    const hay = `${c.label} ${c.keywords || ''} ${c.group || ''}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
}

/** True when a key press came from somewhere the user is typing, so shortcuts must not fire. */
export function isTypingTarget(target) {
  if (!target || typeof target !== 'object') return false;
  const tag = String(target.tagName || '').toLowerCase();
  return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable === true;
}

// "g" then a letter jumps to a page.
export const GO_KEYS = {
  h: { to: '/', label: 'Home' },
  a: { to: '/assess', label: 'Assess a listing' },
  c: { to: '/compare', label: 'Compare' },
  s: { to: '/saved', label: 'Saved assessments' },
  d: { to: '/dashboard', label: 'Dashboard' },
  b: { to: '/about', label: 'About' },
};

export const SHORTCUTS = [
  { keys: ['Ctrl/Cmd', 'K'], text: 'Open the command palette' },
  { keys: ['/'], text: 'Open the command palette' },
  { keys: ['?'], text: 'Show this list' },
  ...Object.entries(GO_KEYS).map(([key, v]) => ({ keys: ['G', key.toUpperCase()], text: `Go to ${v.label}` })),
  { keys: ['Esc'], text: 'Close a dialog' },
];
