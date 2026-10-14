import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * useAsync(fn, { immediate = true, deps = [] })
 * `fn(signal, ...args)` receives an AbortSignal first, then whatever was passed to run(...args).
 * Returns { data, error, loading, run, setData }.
 * - run() never throws: failures land in `error`, so there are no unhandled rejections.
 * - Starting a new run aborts the previous request, and unmounting aborts the current one.
 *   Cancelled requests never touch state, and a stale response can never overwrite a newer one.
 */
export function useAsync(fn, { immediate = true, deps = [] } = {}) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const callId = useRef(0);
  const controllerRef = useRef(null);
  const mounted = useRef(true);
  const [state, setState] = useState({ data: null, error: null, loading: immediate });

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controllerRef.current?.abort();
    };
  }, []);

  const run = useCallback(async (...args) => {
    controllerRef.current?.abort(); // cancel the request this call replaces
    const controller = new AbortController();
    controllerRef.current = controller;
    const id = ++callId.current;
    const current = () => mounted.current && id === callId.current && !controller.signal.aborted;

    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fnRef.current(controller.signal, ...args);
      if (current()) setState({ data, error: null, loading: false });
      return data;
    } catch (error) {
      if (current()) setState((s) => ({ ...s, error, loading: false }));
      return undefined;
    }
  }, []);

  const setData = useCallback((updater) => {
    setState((s) => ({ ...s, data: typeof updater === 'function' ? updater(s.data) : updater }));
  }, []);

  useEffect(() => {
    if (immediate) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [immediate, run, ...deps]);

  return { ...state, run, setData };
}
