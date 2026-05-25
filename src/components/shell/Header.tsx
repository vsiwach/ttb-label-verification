import { NavLink, Link } from 'react-router-dom';

const NAV = [
  { to: '/upload',     label: 'Single label' },
  { to: '/batch',      label: 'Batch' },
];

export default function Header() {
  return (
    <>
      <div className="gov-banner" role="region" aria-label="Official government website">
        <div className="gov-banner__inner">
          <span className="gov-banner__flag" aria-hidden="true" />
          <span>An official prototype of the U.S. Government — Demo data only</span>
        </div>
      </div>
      <header className="site-header" role="banner">
        <div className="site-header__inner">
          <Link to="/upload" className="brand">
            <span className="brand__mark" aria-hidden="true">TTB</span>
            <span className="brand__text">
              <span className="brand__agency">Alcohol &amp; Tobacco Tax and Trade Bureau</span>
              <span className="brand__app">Label Verification</span>
            </span>
          </Link>
          <nav className="nav" aria-label="Primary">
            {NAV.map(l => (
              <NavLink
                key={l.to}
                to={l.to}
                className="nav__link"
                end={l.to === '/upload'}
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
    </>
  );
}
