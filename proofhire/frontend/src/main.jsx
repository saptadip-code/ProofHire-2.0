import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AuthProvider } from './context/AuthContext.jsx';
import { ToastProvider } from './context/ToastContext.jsx';
import { WakeProvider } from './context/WakeContext.jsx';
import './index.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <WakeProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </WakeProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
