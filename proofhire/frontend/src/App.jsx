import { Suspense, lazy, useCallback, useState } from 'react';
import { Route, Routes } from 'react-router-dom';
import CommandPalette from './components/CommandPalette.jsx';
import Footer from './components/Footer.jsx';
import Navbar from './components/Navbar.jsx';
import PageTransition from './components/PageTransition.jsx';
import ProtectedRoute from './components/ProtectedRoute.jsx';
import ShortcutsDialog from './components/ShortcutsDialog.jsx';
import Skeleton from './components/Skeleton.jsx';
import WakeBanner from './components/WakeBanner.jsx';
import { useWake } from './context/WakeContext.jsx';
import { useGlobalShortcuts } from './hooks/useGlobalShortcuts.js';
import { useTheme } from './hooks/useTheme.js';
import About from './pages/About.jsx';
import AdminReports from './pages/AdminReports.jsx';
import Assess from './pages/Assess.jsx';
import AssessmentReport from './pages/AssessmentReport.jsx';
import Landing from './pages/Landing.jsx';
import Login from './pages/Login.jsx';
import NotFound from './pages/NotFound.jsx';
import Register from './pages/Register.jsx';
import Saved from './pages/Saved.jsx';

// Recharts stays out of the first bundle: Dashboard and Compare load on demand (Section C6).
const Dashboard = lazy(() => import('./pages/Dashboard.jsx'));
const Compare = lazy(() => import('./pages/Compare.jsx'));

function RouteFallback() {
  return (
    <div className="container page">
      <Skeleton lines={5} label="Loading page" />
    </div>
  );
}

export default function App() {
  const wake = useWake();
  const { toggle: toggleTheme } = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const openHelp = useCallback(() => setHelpOpen(true), []);
  useGlobalShortcuts({ openPalette, openHelp, enabled: true });
  // The Assess page shows its own banner next to the form; elsewhere it is shown globally.
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Navbar onOpenPalette={openPalette} />
      {wake.showBanner && (
        <div className="container">
          <WakeBanner status={wake.status} attempts={wake.attempts} maxAttempts={wake.maxAttempts} onRetry={wake.retry} />
        </div>
      )}
      <main id="main" className="main" tabIndex={-1}>
        <PageTransition>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/assess" element={<Assess />} />
            <Route path="/assessment/:id" element={<AssessmentReport />} />
            <Route path="/compare" element={<Compare />} />
            <Route
              path="/saved"
              element={
                <ProtectedRoute>
                  <Saved />
                </ProtectedRoute>
              }
            />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route
              path="/admin/reports"
              element={
                <ProtectedRoute role="admin">
                  <AdminReports />
                </ProtectedRoute>
              }
            />
            <Route path="/about" element={<About />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
        </PageTransition>
      </main>
      <Footer />
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onToggleTheme={toggleTheme}
        onShowShortcuts={openHelp}
      />
      <ShortcutsDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </>
  );
}
