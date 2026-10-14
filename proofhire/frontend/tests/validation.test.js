import test from 'node:test';
import assert from 'node:assert/strict';
import { FIELD_LABELS, INITIAL_VALUES, toPayload, validateListing } from '../src/lib/validation.js';

const valid = () => ({ ...INITIAL_VALUES, title: 'Marketing Intern', company_name: 'Acme', description: 'A description that is long enough to pass.' });

test('a minimal valid listing has no errors', () => {
  assert.deepEqual(validateListing(valid()), {});
});
test('required fields and limits are enforced', () => {
  const e = validateListing({ ...valid(), title: 'ab', company_name: 'a', description: 'short' });
  assert.ok(e.title && e.company_name && e.description);
});
test('salary max below min is rejected; non-integers rejected', () => {
  assert.ok(validateListing({ ...valid(), salary_min: '500', salary_max: '100' }).salary_max);
  assert.ok(validateListing({ ...valid(), salary_min: '1.5' }).salary_min);
});
test('email, phone, website, currency, fee checks', () => {
  const e = validateListing({ ...valid(), contact_email: 'nope', contact_phone: 'abc', company_website: 'ftp://x', currency: 'RS', upfront_fee_amount: '-1' });
  for (const k of ['contact_email', 'contact_phone', 'company_website', 'currency', 'upfront_fee_amount']) assert.ok(e[k], k);
});
test('every validated field has a human label for the error summary', () => {
  const e = validateListing({ ...valid(), title: '', salary_min: 'x', contact_email: 'x', upfront_fee_amount: 'x' });
  for (const k of Object.keys(e)) assert.ok(FIELD_LABELS[k], `missing label for ${k}`);
});
test('toPayload sends integers as numbers and blanks as null', () => {
  const p = toPayload({ ...valid(), salary_min: '100', currency: 'inr', location: '  ' });
  assert.equal(p.salary_min, 100);
  assert.equal(p.salary_max, null);
  assert.equal(p.location, null);
  assert.equal(p.currency, 'INR');
  assert.equal(p.upfront_fee_amount, 0);
});
