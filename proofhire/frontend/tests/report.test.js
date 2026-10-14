import test from 'node:test';
import assert from 'node:assert/strict';
import { annotateText, scoreDrivers, sparklinePoints, sortAssessments } from '../src/lib/report.js';
import { filterCommands, isTypingTarget, GO_KEYS } from '../src/lib/palette.js';

const ev = (id, snippet, extra = {}) => ({ id, type: 'observed', direction: 'increases_risk', severity: 3, label: id, snippet, ...extra });

test('annotateText marks snippets in reading order and keeps the rest of the text', () => {
  const text = 'Pay a registration fee of Rs 1,499 now. Message us on WhatsApp.';
  const { segments, unmatched } = annotateText(text, [ev('E2', 'Message us on WhatsApp'), ev('E1', 'registration fee of Rs 1,499')]);
  assert.deepEqual(unmatched, []);
  assert.equal(segments.map((s) => s.text).join(''), text);
  assert.deepEqual(segments.filter((s) => s.id).map((s) => s.id), ['E1', 'E2']);
});
test('annotateText falls back to case-insensitive and lists unmatched or overlapping signals', () => {
  const text = 'Guaranteed Placement after training.';
  const r = annotateText(text, [ev('E1', 'guaranteed placement'), ev('E2', 'hr@gmail.com'), ev('E3', 'placement after')]);
  assert.equal(r.segments.find((s) => s.id).id, 'E1');
  assert.deepEqual(r.unmatched.map((e) => e.id).sort(), ['E2', 'E3']);
});
test('annotateText ignores model items, null snippets and bad input', () => {
  assert.deepEqual(annotateText('abc', [{ id: 'E1', type: 'model', snippet: 'abc' }, ev('E2', null)]).segments, [{ text: 'abc' }]);
  assert.deepEqual(annotateText(undefined, null).segments, []);
});
test('scoreDrivers keeps observed (severity) and model (weight) on separate scales', () => {
  const { observed, model } = scoreDrivers([
    ev('E1', 'x', { severity: 3 }),
    ev('E2', 'y', { severity: 1, direction: 'decreases_risk' }),
    { id: 'E3', type: 'model', direction: 'increases_risk', label: 'm', weight: 2 },
    { id: 'E4', type: 'model', direction: 'decreases_risk', label: 'n', weight: -1 },
    { id: 'E5', type: 'model', direction: 'increases_risk', label: 'no weight', weight: null },
  ]);
  assert.equal(observed[0].id, 'E1');
  assert.equal(observed[0].size, 1);
  assert.equal(model.length, 2);
  assert.equal(model[0].size, 1);
  assert.equal(model[1].size, 0.5);
  assert.deepEqual(scoreDrivers(null), { observed: [], model: [] });
});
test('sparklinePoints needs at least two numbers and stays inside the box', () => {
  assert.equal(sparklinePoints([1]), '');
  const pts = sparklinePoints([0, 5, 10], 80, 24).split(' ').map((p) => p.split(',').map(Number));
  assert.equal(pts.length, 3);
  pts.forEach(([x, y]) => assert.ok(x >= 0 && x <= 80 && y >= 0 && y <= 24));
  assert.ok(sparklinePoints([3, 3, 3]).length > 0);
});
test('sortAssessments sorts without mutating the input', () => {
  const rows = [
    { id: 1, created_at: '2026-01-01T00:00:00Z', risk_score: 0.2, risk_level: 'low' },
    { id: 2, created_at: '2026-03-01T00:00:00Z', risk_score: 0.9, risk_level: 'high' },
    { id: 3, created_at: '2026-02-01T00:00:00Z', risk_score: 0.5, risk_level: 'medium' },
  ];
  const copy = JSON.stringify(rows);
  assert.deepEqual(sortAssessments(rows, 'newest').map((r) => r.id), [2, 3, 1]);
  assert.deepEqual(sortAssessments(rows, 'oldest').map((r) => r.id), [1, 3, 2]);
  assert.deepEqual(sortAssessments(rows, 'risk_desc').map((r) => r.id), [2, 3, 1]);
  assert.deepEqual(sortAssessments(rows, 'level_desc').map((r) => r.id), [2, 3, 1]);
  assert.equal(JSON.stringify(rows), copy);
  assert.deepEqual(sortAssessments(null, 'newest'), []);
});
test('filterCommands needs every typed word; empty query keeps all', () => {
  const cmds = [{ label: 'Saved assessments', keywords: 'history' }, { label: 'Dashboard', group: 'Pages' }];
  assert.equal(filterCommands(cmds, '').length, 2);
  assert.deepEqual(filterCommands(cmds, 'hist sav').map((c) => c.label), ['Saved assessments']);
  assert.equal(filterCommands(cmds, 'zzz').length, 0);
});
test('isTypingTarget and go-keys', () => {
  assert.ok(isTypingTarget({ tagName: 'INPUT' }));
  assert.ok(isTypingTarget({ tagName: 'DIV', isContentEditable: true }));
  assert.equal(isTypingTarget({ tagName: 'BUTTON' }), false);
  assert.equal(isTypingTarget(null), false);
  assert.equal(GO_KEYS.a.to, '/assess');
});
