import { request } from './client.js';

// ---------------------------------------------------------------------------------------------
// ASSUMPTION NOTICE
// The shapes of GET /dashboard/summary (Part B) and metrics.json (Part A) were not available when
// this file was written. The normalizers below accept several plausible key names and return null
// for anything missing, so the UI shows "Not available" instead of inventing values.
// Once Part A / Part B are confirmed, tighten these functions (and ONLY these functions).
// GET /dashboard/trends is defined in Section 5.4: [{date, count, high, medium, low}].
// ---------------------------------------------------------------------------------------------

export const getSummary = (includeDemo = false, { signal } = {}) =>
  request('/dashboard/summary', { auth: false, signal, query: { include_demo: includeDemo ? 'true' : 'false' } });

export const getTrends = (includeDemo = false, days = 14, { signal } = {}) =>
  request('/dashboard/trends', { auth: false, signal, query: { days, include_demo: includeDemo ? 'true' : 'false' } });

export const getModelMetrics = ({ signal } = {}) => request('/dashboard/model-metrics', { auth: false, signal });

const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

function firstNum(obj, keys) {
  if (!obj || typeof obj !== 'object') return null;
  for (const key of keys) {
    const value = num(obj[key]);
    if (value !== null) return value;
  }
  return null;
}

function normalizeDistribution(raw) {
  const src = raw?.by_level ?? raw?.risk_distribution ?? raw?.by_risk_level ?? raw?.risk_levels ?? raw?.distribution;
  if (!src) return null;
  const out = { low: null, medium: null, high: null };
  if (Array.isArray(src)) {
    src.forEach((item) => {
      const level = item?.level ?? item?.risk_level ?? item?.name;
      if (level in out) out[level] = num(item.count ?? item.value);
    });
  } else if (typeof src === 'object') {
    Object.keys(out).forEach((level) => {
      out[level] = num(src[level]);
    });
  }
  return Object.values(out).every((v) => v === null) ? null : out;
}

function normalizeTopEvidence(raw) {
  const src = raw?.top_evidence ?? raw?.top_evidence_codes ?? raw?.top_signals;
  if (!Array.isArray(src)) return [];
  return src
    .map((item) => ({
      label: String(item?.label ?? item?.code ?? item?.name ?? '').trim(),
      count: num(item?.count ?? item?.times_seen ?? item?.n),
    }))
    .filter((item) => item.label && item.count !== null);
}

export function normalizeSummary(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const reports = raw.reports ?? raw.report_counts ?? {};
  return {
    totalAssessments: firstNum(raw, ['total_assessments', 'assessments_total', 'total', 'assessment_count']),
    highRiskCount:
      firstNum(raw, ['high_risk_count', 'high_risk_total']) ?? firstNum(raw?.by_level, ['high']),
    distribution: normalizeDistribution(raw),
    topEvidence: normalizeTopEvidence(raw),
    reportsTotal:
      firstNum(reports, ['total', 'count']) ?? firstNum(raw, ['reports_total', 'report_count', 'total_reports']),
    reportsApproved:
      firstNum(reports, ['approved']) ?? firstNum(raw, ['reports_approved', 'approved_reports', 'report_count_approved']),
    reportsPending: firstNum(reports, ['pending']) ?? firstNum(raw, ['reports_pending', 'pending_reports']),
  };
}

function normalizeConfusion(cm) {
  if (!cm) return null;
  if (Array.isArray(cm) && cm.length === 2 && Array.isArray(cm[0]) && Array.isArray(cm[1])) {
    return { tn: num(cm[0][0]), fp: num(cm[0][1]), fn: num(cm[1][0]), tp: num(cm[1][1]) };
  }
  if (typeof cm === 'object') {
    const out = { tn: num(cm.tn), fp: num(cm.fp), fn: num(cm.fn), tp: num(cm.tp) };
    return Object.values(out).every((v) => v === null) ? null : out;
  }
  return null;
}

export function normalizeMetrics(raw) {
  if (!raw || typeof raw !== 'object') return null;
  // Backend/ML shape (guidebook A11): { synthetic_test: {precision, recall, f1, pr_auc, confusion:[[tn,fp],[fn,tp]]}, ... }
  const src = raw.synthetic_test ?? raw.test ?? raw.holdout ?? raw.metrics ?? raw;
  const limitations = Array.isArray(raw.limitations)
    ? raw.limitations.filter((l) => typeof l === 'string' && l.trim())
    : [];
  return {
    precision: num(src.precision),
    recall: num(src.recall),
    f1: num(src.f1 ?? src.f1_score),
    prAuc: num(src.pr_auc ?? src.average_precision),
    confusion: normalizeConfusion(src.confusion ?? src.confusion_matrix ?? raw.confusion_matrix),
    limitations,
  };
}

export function normalizeTrends(raw) {
  const list = Array.isArray(raw) ? raw : Array.isArray(raw?.items) ? raw.items : [];
  return list.map((row) => ({
    date: String(row?.date ?? ''),
    count: num(row?.count) ?? 0,
    high: num(row?.high) ?? 0,
    medium: num(row?.medium) ?? 0,
    low: num(row?.low) ?? 0,
  }));
}
