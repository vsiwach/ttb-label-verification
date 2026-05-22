import { useEffect, useRef, useState } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import Header from './components/shell/Header';
import Footer from './components/shell/Footer';
import UploadPage from './pages/UploadPage';
import ResultPage from './pages/ResultPage';
import BatchPage from './pages/BatchPage';
import ReviewPage from './pages/ReviewPage';
import SystemPage from './pages/SystemPage';
import StyleGuidePage from './pages/StyleGuidePage';
import ApiDemoPage from './pages/ApiDemoPage';

const ROUTE_TITLES: Record<string, string> = {
  '/upload':     'Verify a label',
  '/result':     'Verification result',
  '/batch':      'Review a batch',
  '/review':     'Confirm next',
  '/system':     'Design system and API contract',
  '/styleguide': 'Component styleguide',
  '/api-demo':   'Streaming API demo',
};

export default function App() {
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const [routeAnnounce, setRouteAnnounce] = useState('');
  const prevPath = useRef(location.pathname);

  // On route change, move focus to main + announce to AT.
  useEffect(() => {
    if (prevPath.current === location.pathname) return;
    prevPath.current = location.pathname;
    const title = ROUTE_TITLES[location.pathname] || location.pathname;
    setRouteAnnounce(`Navigated to: ${title}`);
    requestAnimationFrame(() => mainRef.current?.focus());
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
          <Route path="/system"     element={<SystemPage />} />
          <Route path="/styleguide" element={<StyleGuidePage />} />
          <Route path="/api-demo"   element={<ApiDemoPage />} />
          <Route path="*"           element={<UploadPage />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
