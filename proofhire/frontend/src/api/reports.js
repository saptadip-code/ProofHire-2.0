import { request } from './client.js';

// POST /reports: anonymous callers are allowed (auth is optional).
export const createReport = ({ assessment_id, report_type, description }, { signal } = {}) =>
  request('/reports', { method: 'POST', body: { assessment_id, report_type, description }, signal });

export const listMyReports = ({ signal } = {}) => request('/reports/mine', { signal });

// Admin moderation (GET/PATCH /admin/reports). The backend enforces the admin role; the UI only hides it.
export const listAdminReports = ({ status = 'pending', page = 1, limit = 20 } = {}, { signal } = {}) =>
  request('/admin/reports', { query: { status, page, limit }, signal });

export const reviewReport = (id, { status, moderator_note }, { signal } = {}) =>
  request(`/admin/reports/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: { status, moderator_note },
    signal,
  });
