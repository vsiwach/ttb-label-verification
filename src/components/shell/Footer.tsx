import { Link } from 'react-router-dom';

export default function Footer() {
  return (
    <footer className="site-footer" role="contentinfo">
      <div className="site-footer__inner">
        <div>
          <h3 className="site-footer__title">TTB Label Verification</h3>
          <p className="site-footer__meta" style={{ maxWidth: 'none' }}>
            A frontend prototype for the Alcohol and Tobacco Tax and Trade Bureau's
            AI-assisted label compliance review tool. Backend is mocked.
          </p>
          <p className="site-footer__meta" style={{ marginTop: 16 }}>
            Section 508 / WCAG 2.1–2.2 AA compliant. USWDS visual conventions.
          </p>
        </div>
        <div>
          <h4 style={{ color: '#fff', fontSize: 14, textTransform: 'uppercase', letterSpacing: '.06em', margin: '0 0 8px' }}>Regulations</h4>
          <ul>
            <li><Link to="/system">27 CFR Part 4 (Wine)</Link></li>
            <li><Link to="/system">27 CFR Part 5 (Spirits)</Link></li>
            <li><Link to="/system">27 CFR Part 7 (Malt)</Link></li>
            <li><Link to="/system">27 CFR 16.21–16.22 (Health warning)</Link></li>
          </ul>
        </div>
        <div>
          <h4 style={{ color: '#fff', fontSize: 14, textTransform: 'uppercase', letterSpacing: '.06em', margin: '0 0 8px' }}>Resources</h4>
          <ul>
            <li><Link to="/system">Design system</Link></li>
            <li><Link to="/system">API contract</Link></li>
            <li><Link to="/styleguide">Component library</Link></li>
            <li><Link to="/api-demo">Streaming API demo</Link></li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
