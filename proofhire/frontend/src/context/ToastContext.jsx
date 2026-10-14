import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Check, Info, X } from 'lucide-react';

const ToastContext = createContext({ push: () => {} });
export const useToast = () => useContext(ToastContext);

// Global, stacked toasts. `push(message, { tone: 'success' | 'info', duration })`.
// The region is a polite live region, so screen readers hear each message once.
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id) => setToasts((list) => list.filter((t) => t.id !== id)), []);
  const push = useCallback((message, { tone = 'success', duration = 5000 } = {}) => {
    if (!message) return;
    const id = nextId.current++;
    setToasts((list) => [...list.slice(-3), { id, message, tone, duration }]);
  }, []);

  const value = useMemo(() => ({ push }), [push]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" role="region" aria-label="Notifications" aria-live="polite">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onClose={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onClose }) {
  useEffect(() => {
    const timer = setTimeout(onClose, toast.duration);
    return () => clearTimeout(timer);
  }, [toast.duration, onClose]);
  const Icon = toast.tone === 'info' ? Info : Check;
  return (
    <div className={`toast toast--${toast.tone}`} role="status">
      <Icon size={18} aria-hidden="true" />
      <span>{toast.message}</span>
      <button type="button" className="icon-btn" onClick={onClose} aria-label="Dismiss message">
        <X size={16} aria-hidden="true" />
      </button>
    </div>
  );
}
