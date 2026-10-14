// Small, dependency-free formatting and error-description helpers.

export function formatPercent(score, digits = 0) {
  if (typeof score !== 'number' || Number.isNaN(score)) return '—';
  return `${(score * 100).toFixed(digits)}%`;
}

export function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatShortDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

export function formatInr(amount) {
  if (typeof amount !== 'number' || Number.isNaN(amount)) return '—';
  return `₹${amount.toLocaleString('en-IN')}`;
}

export function formatMetric(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'Not available';
  return value.toFixed(3);
}

export function formatCount(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  return value.toLocaleString('en-IN');
}

export function formatCell(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return value.toLocaleString('en-IN');
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return '—';
    }
  }
  return String(value);
}

export function salaryRange(listing) {
  if (!listing) return '—';
  const { salary_min: min, salary_max: max, pay_period: period } = listing;
  const suffix = period === 'year' ? ' / year' : period === 'one_time' ? ' (one-time)' : ' / month';
  if (min == null && max == null) return 'Not stated';
  if (min != null && max != null) {
    return min === max
      ? `${formatInr(min)}${suffix}`
      : `${formatInr(min)} – ${formatInr(max)}${suffix}`;
  }
  return `${formatInr(min ?? max)}${suffix}`;
}

// Turns any thrown value into text a student can act on. Never leaks stack traces.
export function describeError(error) {
  if (!error) return 'Something went wrong. Please try again.';
  if (typeof error === 'string') return error;
  switch (error.code) {
    case 'timeout':
      return 'The server took too long to respond. It may still be waking up, so please try again in a moment.';
    case 'network_error':
      return 'Could not reach the server. Check your connection and try again.';
    case 'rate_limited':
      return 'You have sent too many assessments in a short time. Please wait a minute and try again.';
    case 'model_unavailable':
      return 'The risk model is not loaded on the server right now. Please try again shortly.';
    case 'unauthorized':
      return 'Your session has expired or you are not signed in. Please sign in and try again.';
    case 'forbidden':
      return 'You do not have permission to do that.';
    case 'not_found':
      return error.message || 'We could not find what you were looking for.';
    default:
      return error.message || 'Something went wrong. Please try again.';
  }
}

export function pluralize(count, singular, plural) {
  return count === 1 ? singular : plural || `${singular}s`;
}
