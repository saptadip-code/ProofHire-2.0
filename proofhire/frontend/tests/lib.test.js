import test from 'node:test';
import assert from 'node:assert/strict';
import { describeError, salaryRange, pluralize } from '../src/lib/format.js';
import { boundaryNote, explainEvidence, levelGuidance, missingListingDetails } from '../src/lib/insights.js';
import { normalizeMetrics, normalizeSummary, normalizeTrends } from '../src/api/dashboard.js';

test('describeError gives friendly text and never throws on odd input', () => {
  assert.match(describeError({ code: 'timeout' }), /took too long/);
  assert.match(describeError({ code: 'network_error' }), /Could not reach/);
  assert.ok(describeError(null));
  assert.equal(describeError('plain'), 'plain');
  assert.equal(describeError({ code: 'weird', message: 'Custom' }), 'Custom');
});
test('pluralize and salaryRange', () => {
  assert.equal(pluralize(1, 'item'), 'item');
  assert.equal(pluralize(2, 'item'), 'items');
  assert.ok(typeof salaryRange({}) === 'string');
});
test('levelGuidance covers each level and an unknown one', () => {
  for (const l of ['low', 'medium', 'high']) assert.ok(levelGuidance(l));
  assert.match(levelGuidance('???'), /could not be read/);
});
test('boundaryNote only fires near a threshold and ignores bad input', () => {
  const t = { low: 0.3, high: 0.6 };
  assert.ok(boundaryNote(0.62, t));
  assert.equal(boundaryNote(0.9, t), null);
  assert.equal(boundaryNote('x', t), null);
  assert.equal(boundaryNote(0.5, undefined), null);
});
test('explainEvidence and missingListingDetails tolerate sparse data', () => {
  assert.ok(Array.isArray(explainEvidence({})));
  assert.ok(Array.isArray(missingListingDetails({})));
  assert.ok(Array.isArray(missingListingDetails(null)));
});
test('dashboard normalizers survive unknown shapes', () => {
  assert.equal(normalizeSummary(null), null);
  assert.ok(normalizeSummary({}));
  assert.ok(normalizeSummary({ total_assessments: 5, high_risk_count: 2 }).totalAssessments === 5);
  assert.doesNotThrow(() => normalizeMetrics({}));
  assert.doesNotThrow(() => normalizeMetrics(null));
  assert.doesNotThrow(() => normalizeTrends({}));
  assert.doesNotThrow(() => normalizeTrends(null));
});

// Integration: shapes taken from the real backend (schemas/dashboard.py) and ml/artifacts/metrics.json.
test('normalizeSummary reads the backend DashboardSummary shape (by_level, reports.*)', () => {
  const s = normalizeSummary({
    total_assessments: 7,
    by_level: { low: 2, medium: 1, high: 4 },
    top_evidence: [{ code: 'UPFRONT_FEE', label: 'Asks the applicant to pay money', count: 3 }],
    reports: { total: 5, pending: 2, approved: 2, rejected: 1 },
  });
  assert.equal(s.totalAssessments, 7);
  assert.equal(s.highRiskCount, 4);
  assert.deepEqual(s.distribution, { low: 2, medium: 1, high: 4 });
  assert.equal(s.reportsApproved, 2);
  assert.equal(s.reportsPending, 2);
  assert.equal(s.topEvidence[0].count, 3);
});

test('normalizeMetrics reads the metrics.json shape (synthetic_test.confusion)', () => {
  const m = normalizeMetrics({
    synthetic_test: { precision: 0.9822, recall: 0.8818, f1: 0.9293, pr_auc: 0.9777, confusion: [[549, 5], [37, 276]] },
    limitations: ['SYNTHETIC BENCHMARK: example'],
  });
  assert.equal(m.precision, 0.9822);
  assert.equal(m.prAuc, 0.9777);
  assert.deepEqual(m.confusion, { tn: 549, fp: 5, fn: 37, tp: 276 });
  assert.equal(m.limitations.length, 1);
});
