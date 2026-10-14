import test from 'node:test';
import assert from 'node:assert/strict';
import { installBrowserStubs, mockFetch } from './helpers.js';

const { store, events } = installBrowserStubs();
const { request, ApiError, SESSION_EXPIRED_EVENT } = await import('../src/api/client.js');
const { createAssessment, normalizeAssessment } = await import('../src/api/assessments.js');

test.beforeEach(() => { store.clear(); events.length = 0; });

test('maps the Section 5.5 error shape', async () => {
  mockFetch(() => ({ status: 422, body: { error: { code: 'validation_error', message: 'Bad', fields: [{ field: 'title', message: 'Too short' }] } } }));
  await assert.rejects(request('/x'), (e) => e instanceof ApiError && e.code === 'validation_error' && e.status === 422);
});
test('handles 204 and non-JSON bodies', async () => {
  mockFetch(() => ({ status: 204 }));
  assert.equal(await request('/x', { method: 'DELETE' }), null);
  mockFetch(() => ({ status: 200, body: '<html>' }));
  await assert.rejects(request('/x'), (e) => e.code === 'bad_response');
});
test('network failure becomes network_error', async () => {
  mockFetch(() => { throw new TypeError('fail'); });
  await assert.rejects(request('/x'), (e) => e.code === 'network_error');
});
test('timeout and caller cancellation are distinct', async () => {
  globalThis.fetch = (url, init) => new Promise((_, rej) => init.signal.addEventListener('abort', () => rej(Object.assign(new Error('a'), { name: 'AbortError' }))));
  await assert.rejects(request('/x', { timeoutMs: 20 }), (e) => e.code === 'timeout');
  const c = new AbortController();
  const p = request('/x', { signal: c.signal });
  c.abort();
  await assert.rejects(p, (e) => e.code === 'cancelled');
});
test('sends Bearer and X-Owner-Token headers', async () => {
  store.set('ph_token', 'tok');
  store.set('ph_owner_tokens', JSON.stringify({ 'abc': 'own' }));
  const calls = mockFetch(() => ({ body: {} }));
  await request('/x', { ownerAssessmentId: 'abc' });
  assert.equal(calls[0].init.headers.Authorization, 'Bearer tok');
  assert.equal(calls[0].init.headers['X-Owner-Token'], 'own');
});
test('401 with a token fires the session-expired event; without a token it does not', async () => {
  mockFetch(() => ({ status: 401, body: { error: { code: 'unauthorized', message: 'no' } } }));
  await assert.rejects(request('/x'));
  assert.deepEqual(events, []);
  store.set('ph_token', 'tok');
  await assert.rejects(request('/x'));
  assert.deepEqual(events, [SESSION_EXPIRED_EVENT]);
});
test('createAssessment stores the one-time owner_token', async () => {
  mockFetch(() => ({ status: 201, body: { assessment_id: 'a1', owner_token: 'secret', evidence: null } }));
  const r = await createAssessment({ title: 't' });
  assert.equal(r.assessment_id, 'a1');
  assert.equal(JSON.parse(store.get('ph_owner_tokens')).a1, 'secret');
});
test('normalizeAssessment defaults arrays and rejects non-assessments', () => {
  const n = normalizeAssessment({ assessment_id: 'a', evidence: null, explanation: 'x' });
  assert.deepEqual(n.evidence, []);
  assert.deepEqual(n.checklist, []);
  assert.equal(n.explanation, null);
  assert.throws(() => normalizeAssessment({}), (e) => e.code === 'bad_response');
  assert.throws(() => normalizeAssessment(null));
});
