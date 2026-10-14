import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as authApi from '../api/auth.js';
import { SESSION_EXPIRED_EVENT, storage } from '../api/client.js';
import { STORAGE_KEYS } from '../lib/constants.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => storage.get(STORAGE_KEYS.token));
  const [user, setUser] = useState(() => storage.getJson(STORAGE_KEYS.user, null));
  // `ready` is false only while a stored token is being checked with GET /auth/me.
  const [ready, setReady] = useState(() => !storage.get(STORAGE_KEYS.token));
  // True after the server rejected our token (401) so the sign-in page can explain why.
  const [sessionExpired, setSessionExpired] = useState(false);

  const clear = useCallback(() => {
    storage.remove(STORAGE_KEYS.token);
    storage.remove(STORAGE_KEYS.user);
    setToken(null);
    setUser(null);
  }, []);

  const persist = useCallback((accessToken, nextUser) => {
    setSessionExpired(false);
    storage.set(STORAGE_KEYS.token, accessToken);
    storage.setJson(STORAGE_KEYS.user, nextUser);
    setToken(accessToken);
    setUser(nextUser);
  }, []);

  // Any authenticated request that returns 401 ends the session everywhere in the app.
  useEffect(() => {
    const onExpired = () => {
      clear();
      setSessionExpired(true);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [clear]);

  // On load, validate a stored token. A 401 clears it; other failures keep the cached user.
  useEffect(() => {
    if (!storage.get(STORAGE_KEYS.token)) {
      setReady(true);
      return undefined;
    }
    let cancelled = false;
    authApi
      .getMe()
      .then((me) => {
        if (cancelled) return;
        setUser(me);
        storage.setJson(STORAGE_KEYS.user, me);
      })
      .catch((error) => {
        if (!cancelled && error && error.status === 401) clear();
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [clear]);

  const login = useCallback(
    async (credentials) => {
      const result = await authApi.login(credentials);
      persist(result.access_token, result.user);
      return result.user;
    },
    [persist],
  );

  const register = useCallback(
    async (details) => {
      const result = await authApi.register(details);
      persist(result.access_token, result.user);
      return result.user;
    },
    [persist],
  );

  const value = useMemo(
    () => ({ user, token, ready, sessionExpired, login, register, logout: clear }),
    [user, token, ready, sessionExpired, login, register, clear],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>.');
  return ctx;
}
