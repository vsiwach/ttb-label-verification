import { useEffect, useRef, useState } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import Header from './components/shell/Header';
import Footer from './components/shell/Footer';
import UploadPage from './pages/UploadPage';
import ResultPage from './pages/ResultPage';
import BatchPage from './pages/BatchPage';
import ReviewPage from './pages/ReviewPage';
import SamplesPage from './pages/SamplesPage';
import { preWarmModal } from './utils/preWarm';

const ROUTE_TITLES: Record<string, string> = {
  '/upload':     'Verify a label',
  '/result':     'Verification result',
  '/batch':      'Review a batch',
  '/review':     'Confirm next',
  '/samples':    'Sample directory',
};

export default function App() {
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const [routeAnnounce, setRouteAnnounce] = useState('');
  const prevPath = useRef(location.pathname);

  // Pre-warm Modal the instant anyone opens the app — gallery, result
  // page, single, batch, anywhere. The /health probe kicks the GPU
  // container awake server-side so by the time the agent navigates to
  // /upload and submits a verify, Modal is warm and the call lands at
  // the ~5s warm target instead of the ~9s cold-start path.
  useEffect(() => { preWarmModal(); }, []);

  // On route change, move focus to main + announce to AT.
  useEffect(() => {
    if (prevPath.current === location.pathname) return;
    prevPath.current = location.pathname;
    const title = ROUTE_TITLES[location.pathname] || location.pathname;
    setRouteAnnounce(`Navigated to: ${title}`);
    requestAnimationFrame(() => mainRef.current?.focus());
    // Re-warm on every route change too — cheap (60s cooldown in
    // preWarm.ts dedupes back-to-back nav) and saves the agent from a
    // cold start if they spent >5 min on one page before navigating.
    preWarmModal();
  }, [location.pathname]);

  return (
    <div className="app">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <Header />
      <p className="sr-only" role="status" aria-live="polite">{routeAnnounce}</p>
      <main
        id="main-content"
        ref={mainRef}
        tabIndex={-1}
        data-screen-label={location.pathname}
        style={{ outline: 'none' }}
      >
        <Routes>
          <Route path="/"           element={<UploadPage />} />
          <Route path="/upload"     element={<UploadPage />} />
          <Route path="/result"     element={<ResultPage />} />
          <Route path="/batch"      element={<BatchPage />} />
          <Route path="/review"     element={<ReviewPage />} />
          <Route path="/samples"    element={<SamplesPage />} />
          <Route path="*"           element={<UploadPage />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
