import { useCallback, useEffect, useRef, useState } from 'react';
import { getHealth } from '../api/client.js';

// Render's free tier sleeps after 15 min idle and takes about a minute to wake (Section C1).
const SHOW_BANNER_AFTER_MS = 3000;
const RETRY_EVERY_MS = 5000;
export const MAX_WAKE_ATTEMPTS = 12;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Calls GET /health on app load.
 * status: 'pending' (still trying) | 'ready' (health OK) | 'unreachable' (retries exhausted)
 * showBanner: true once pending for more than 3 s.
 */
export function useWakeServer() {
  const [status, setStatus] = useState('pending');
  const [attempts, setAttempts] = useState(0);
  const [slow, setSlow] = useState(false);
  const [health, setHealth] = useState(null);
  const runId = useRef(0);

  const start = useCallback(() => {
    const id = ++runId.current;
    setStatus('pending');
    setAttempts(0);
    setSlow(false);

    const slowTimer = setTimeout(() => {
      if (runId.current === id) setSlow(true);
    }, SHOW_BANNER_AFTER_MS);

    (async () => {
      for (let attempt = 1; attempt <= MAX_WAKE_ATTEMPTS; attempt += 1) {
        if (runId.current !== id) return;
        setAttempts(attempt);
        try {
          const result = await getHealth();
          if (runId.current !== id) return;
          clearTimeout(slowTimer);
          setHealth(result);
          setStatus('ready');
          setSlow(false);
          return;
        } catch {
          if (attempt < MAX_WAKE_ATTEMPTS) await sleep(RETRY_EVERY_MS);
        }
      }
      if (runId.current === id) {
        clearTimeout(slowTimer);
        setSlow(false);
        setStatus('unreachable');
      }
    })();
  }, []);

  useEffect(() => {
    start();
    return () => {
      runId.current += 1; // cancels any in-flight loop
    };
  }, [start]);

  return {
    status,
    attempts,
    maxAttempts: MAX_WAKE_ATTEMPTS,
    showBanner: status === 'pending' ? slow : status === 'unreachable',
    health,
    retry: start,
  };
}
