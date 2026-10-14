import { request } from './client.js';

export const register = ({ email, password, display_name }) =>
  request('/auth/register', { method: 'POST', body: { email, password, display_name }, auth: false });

export const login = ({ email, password }) =>
  request('/auth/login', { method: 'POST', body: { email, password }, auth: false });

export const getMe = () => request('/auth/me');
