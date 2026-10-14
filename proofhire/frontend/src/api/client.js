import { STORAGE_KEYS } from '../lib/constants.js';

// `?.` keeps this module loadable outside Vite (the dependency-free tests run it under plain Node).
const API_BASE = (import.meta.env?.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/+$/, '');
const TIMEOUT_MS = 20000;

// Fired when an authenticated request comes back 401, so AuthContext can end the session.
export const SESSION_EXPIRED_EVENT = 'ph:session-expired';

function notifySessionExpired() {
  try {
    if (typeof window !== 'undefined' && typeof CustomEvent === 'function') {
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
    }
  } catch {
    /* ignore */
  }
}

// ---- localStorage helpers: every access is wrapped in try/catch (private mode, blocked storage). ----

export const storage = {
  get(key, fallback = null) {
    try {
      const value = window.localStorage.getItem(key);
      return value === null ? fallback : value;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      window.localStorage.setItem(key, value);
      return true;
    } catch {
      return false;
    }
  },
  remove(key) {
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  },
  getJson(key, fallback = null) {
    const raw = storage.get(key);
    if (raw === null) return fallback;
    try {
      return JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  setJson(key, value) {
    try {
      return storage.set(key, JSON.stringify(value));
    } catch {
      return false;
    }
  },
};

export const getToken = () => storage.get(STORAGE_KEYS.token);

function readOwnerTokens() {
  const map = storage.getJson(STORAGE_KEYS.ownerTokens, {});
  return map && typeof map === 'object' && !Array.isArray(map) ? map : {};
}

export function getOwnerToken(assessmentId) {
  return readOwnerTokens()[String(assessmentId)] ?? null;
}

export function saveOwnerToken(assessmentId, token) {
  const map = readOwnerTokens();
  map[String(assessmentId)] = token;
  storage.setJson(STORAGE_KEYS.ownerTokens, map);
}

export function removeOwnerToken(assessmentId) {
  const map = readOwnerTokens();
  delete map[String(assessmentId)];
  storage.setJson(STORAGE_KEYS.ownerTokens, map);
}

// ---- Errors: Section 5.5 shape -> ApiError{code, message, fields, status} ----

export class ApiError extends Error {
  constructor({ code = 'internal_error', message = 'Something went wrong.', fields = [], status = 0 } = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.fields = Array.isArray(fields) ? fields : [];
    this.status = status;
  }
}

const CODE_BY_STATUS = {
  400: 'bad_request',
  401: 'unauthorized',
  403: 'forbidden',
  404: 'not_found',
  409: 'conflict',
  422: 'validation_error',
  429: 'rate_limited',
  503: 'model_unavailable',
};

function toApiError(status, data) {
  const err = data && typeof data === 'object' ? data.error : null;
  if (err && typeof err === 'object') {
    return new ApiError({
      code: err.code || CODE_BY_STATUS[status] || 'internal_error',
      message: err.message || 'Request failed.',
      fields: err.fields,
      status,
    });
  }
  // Unwrapped FastAPI default 422: { detail: [{ loc, msg }] }
  if (data && Array.isArray(data.detail)) {
    const fields = data.detail.map((d) => ({
      field: Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1]) : '',
      message: d.msg || 'Invalid value',
    }));
    return new ApiError({
      code: 'validation_error',
      message: fields[0] ? `${fields[0].field}: ${fields[0].message}` : 'Validation failed.',
      fields,
      status,
    });
  }
  return new ApiError({
    code: CODE_BY_STATUS[status] || 'internal_error',
    message: status >= 500 ? 'The server had a problem. Please try again.' : 'Request failed.',
    status,
  });
}

function buildUrl(path, query) {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  if (!query) return url;
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.append(key, String(value));
  });
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

/**
 * request(path, options)
 *  - auth: send Authorization: Bearer <ph_token> when a token exists (default true)
 *  - ownerAssessmentId: send X-Owner-Token for that assessment when one is stored
 *  - 20 s timeout via AbortController
 *  - signal: an AbortSignal from the caller. Aborting it rejects with ApiError code 'cancelled'
 *    (distinct from 'timeout'), which useAsync treats as "ignore, a newer request replaced this one"
 *  - a 401 on a request that sent a token fires SESSION_EXPIRED_EVENT
 */
export async function request(
  path,
  { method = 'GET', body, query, auth = true, ownerAssessmentId, timeoutMs = TIMEOUT_MS, signal } = {},
) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  if (ownerAssessmentId !== undefined && ownerAssessmentId !== null) {
    const ownerToken = getOwnerToken(ownerAssessmentId);
    if (ownerToken) headers['X-Owner-Token'] = ownerToken;
  }

  const sentToken = Boolean(headers.Authorization);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let cancelled = false;
  const onCallerAbort = () => {
    cancelled = true;
    controller.abort();
  };
  if (signal) {
    if (signal.aborted) onCallerAbort();
    else signal.addEventListener('abort', onCallerAbort, { once: true });
  }

  try {
    const response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (response.status === 204) return null;

    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }

    if (!response.ok) {
      if (response.status === 401 && sentToken) notifySessionExpired();
      throw toApiError(response.status, data);
    }
    if (data === null && text) {
      throw new ApiError({ code: 'bad_response', message: 'The server sent an unreadable response.', status: response.status });
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error && error.name === 'AbortError') {
      if (cancelled) throw new ApiError({ code: 'cancelled', message: 'Request cancelled.', status: 0 });
      throw new ApiError({ code: 'timeout', message: 'The request timed out after 20 seconds.', status: 0 });
    }
    throw new ApiError({ code: 'network_error', message: 'Could not reach the server.', status: 0 });
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', onCallerAbort);
  }
}

// GET /health is public and is used by useWakeServer.
export const getHealth = () => request('/health', { auth: false });
