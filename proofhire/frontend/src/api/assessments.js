import { ApiError, request, saveOwnerToken, removeOwnerToken } from './client.js';

const enc = encodeURIComponent;

const asArray = (value) => (Array.isArray(value) ? value : []);

/**
 * Defensive normalizer for an AssessmentResult (Section 5.4). It never invents values: it only makes
 * sure the collections the UI iterates are arrays and that the response is an object with an id.
 * Anything else the server sends is passed through untouched.
 * @throws {ApiError} code 'bad_response' when the payload is not usable
 */
export function normalizeAssessment(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw) || raw.assessment_id === undefined || raw.assessment_id === null) {
    throw new ApiError({ code: 'bad_response', message: 'The server sent an assessment in an unexpected format.', status: 200 });
  }
  return {
    ...raw,
    evidence: asArray(raw.evidence).filter((item) => item && typeof item === 'object'),
    checklist: asArray(raw.checklist).filter((item) => item && typeof item === 'object'),
    connections: asArray(raw.connections).filter((item) => item && typeof item === 'object'),
    entities: asArray(raw.entities),
    explanation: raw.explanation && typeof raw.explanation === 'object' ? raw.explanation : null,
    listing: raw.listing && typeof raw.listing === 'object' ? raw.listing : null,
  };
}

// POST /assessments. Anonymous callers receive a one-time owner_token: store it before returning.
export async function createAssessment(listing, { signal } = {}) {
  const result = await request('/assessments', { method: 'POST', body: listing, signal });
  if (result && result.owner_token && result.assessment_id !== undefined && result.assessment_id !== null) {
    saveOwnerToken(result.assessment_id, result.owner_token);
  }
  return result;
}

export const getAssessment = async (id, { signal } = {}) =>
  normalizeAssessment(await request(`/assessments/${enc(id)}`, { ownerAssessmentId: id, signal }));

export const listAssessments = ({ page = 1, limit = 20, riskLevel = '' } = {}, { signal } = {}) =>
  request('/assessments', { query: { page, limit, risk_level: riskLevel }, signal });

export async function deleteAssessment(id, { signal } = {}) {
  await request(`/assessments/${enc(id)}`, { method: 'DELETE', ownerAssessmentId: id, signal });
  removeOwnerToken(id);
}

export const setChecklistItemDone = (assessmentId, itemId, done, { signal } = {}) =>
  request(`/assessments/${enc(assessmentId)}/checklist/${enc(itemId)}`, {
    method: 'PATCH',
    body: { done },
    ownerAssessmentId: assessmentId,
    signal,
  });

export const compareAssessments = (assessmentIdA, assessmentIdB, { signal } = {}) =>
  request('/assessments/compare', {
    method: 'POST',
    body: { assessment_id_a: assessmentIdA, assessment_id_b: assessmentIdB },
    signal,
  });
