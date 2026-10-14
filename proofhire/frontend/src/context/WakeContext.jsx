import { createContext, useContext } from 'react';
import { useWakeServer } from '../hooks/useWakeServer.js';

const WakeContext = createContext(null);

// One health check for the whole app; pages read it to decide whether the Analyse button is enabled.
export function WakeProvider({ children }) {
  const wake = useWakeServer();
  return <WakeContext.Provider value={wake}>{children}</WakeContext.Provider>;
}

export function useWake() {
  const ctx = useContext(WakeContext);
  if (!ctx) throw new Error('useWake must be used inside <WakeProvider>.');
  return ctx;
}
