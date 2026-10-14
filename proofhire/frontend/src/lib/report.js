// Pure helpers for the report visuals. Everything is derived from fields the API returns.

/**
 * Splits `text` around the evidence snippets found in it so they can be marked.
 * Returns { segments, unmatched }:
 *  - segments: [{ text } | { text, id, direction }] in reading order
 *  - unmatched: evidence items that have a snippet which was not found in the text, or that
 *    overlapped an earlier mark (they are listed separately rather than dropped)
 * Matching is exact first, then case-insensitive.
 */
export function annotateText(text, evidence) {
  const source = typeof text === 'string' ? text : '';
  const items = (Array.isArray(evidence) ? evidence : []).filter(
    (e) => e && e.type === 'observed' && typeof e.snippet === 'string' && e.snippet.trim() !== '',
  );
  const lower = source.toLowerCase();
  const found = [];
  const unmatched = [];

  items.forEach((e) => {
    let start = source.indexOf(e.snippet);
    if (start < 0) start = lower.indexOf(e.snippet.toLowerCase());
    if (start < 0) unmatched.push(e);
    else found.push({ start, end: start + e.snippet.length, item: e });
  });
  found.sort((a, b) => a.start - b.start || b.end - a.end);

  const segments = [];
  let cursor = 0;
  found.forEach((m) => {
    if (m.start < cursor) {
      unmatched.push(m.item); // overlaps a previous mark
      return;
    }
    if (m.start > cursor) segments.push({ text: source.slice(cursor, m.start) });
    segments.push({ text: source.slice(m.start, m.end), id: m.item.id, direction: m.item.direction });
    cursor = m.end;
  });
  if (cursor < source.length) segments.push({ text: source.slice(cursor) });
  return { segments, unmatched };
}

/**
 * Groups evidence for the "what moved the score" bars. Observed signals are scaled by severity
 * (1 to 3) and model signals by their model weight. The two scales are different, so they are
 * never mixed into one bar chart.
 */
export function scoreDrivers(evidence) {
  const list = Array.isArray(evidence) ? evidence.filter((e) => e && typeof e === 'object') : [];
  const up = (e) => e.direction === 'increases_risk';

  const observed = list
    .filter((e) => e.type === 'observed')
    .map((e) => ({ id: e.id, label: e.label, increases: up(e), size: clamp(Number(e.severity) || 0, 0, 3) / 3, text: `Severity ${clamp(Number(e.severity) || 0, 0, 3)} of 3` }))
    .sort((a, b) => Number(b.increases) - Number(a.increases) || b.size - a.size);

  const modelItems = list.filter((e) => e.type === 'model' && typeof e.weight === 'number');
  const maxWeight = Math.max(0, ...modelItems.map((e) => Math.abs(e.weight))) || 1;
  const model = modelItems
    .map((e) => ({ id: e.id, label: e.label, increases: up(e), size: Math.abs(e.weight) / maxWeight, text: `Weight ${e.weight.toFixed(2)}` }))
    .sort((a, b) => Number(b.increases) - Number(a.increases) || b.size - a.size);

  return { observed, model };
}

function clamp(n, lo, hi) {
  return Math.min(hi, Math.max(lo, n));
}

/** Points for a tiny inline sparkline: values -> "x,y" pairs in a width x height box. */
export function sparklinePoints(values, width = 80, height = 24, pad = 2) {
  const nums = (Array.isArray(values) ? values : []).map(Number).filter((n) => Number.isFinite(n));
  if (nums.length < 2) return '';
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  return nums
    .map((n, i) => {
      const x = pad + (i / (nums.length - 1)) * (width - pad * 2);
      const y = height - pad - ((n - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

/** Sorts saved-assessment rows by a key without mutating the input. */
export function sortAssessments(items, sort) {
  const list = Array.isArray(items) ? [...items] : [];
  const level = { high: 3, medium: 2, low: 1 };
  const time = (i) => Date.parse(i?.created_at) || 0;
  if (sort === 'risk_desc') return list.sort((a, b) => (Number(b.risk_score) || 0) - (Number(a.risk_score) || 0));
  if (sort === 'risk_asc') return list.sort((a, b) => (Number(a.risk_score) || 0) - (Number(b.risk_score) || 0));
  if (sort === 'level_desc') return list.sort((a, b) => (level[b.risk_level] || 0) - (level[a.risk_level] || 0) || time(b) - time(a));
  if (sort === 'oldest') return list.sort((a, b) => time(a) - time(b));
  return list.sort((a, b) => time(b) - time(a)); // newest first (default)
}
