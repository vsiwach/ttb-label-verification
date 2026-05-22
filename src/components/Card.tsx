import type { CSSProperties, ReactNode } from 'react';

export interface CardProps {
  title?: ReactNode;
  titleLevel?: 1 | 2 | 3 | 4 | 5 | 6;
  headerSlot?: ReactNode;
  footerSlot?: ReactNode;
  padding?: number | string;
  style?: CSSProperties;
  children?: ReactNode;
}

export default function Card({
  title, titleLevel = 3, headerSlot, footerSlot, padding, style, children,
}: CardProps) {
  const Heading = (`h${titleLevel}` as keyof JSX.IntrinsicElements);
  const hasHeader = title || headerSlot;
  return (
    <section className={`card${hasHeader || footerSlot ? ' card--flush' : ''}`} style={style}>
      {hasHeader && (
        <div className="card__header">
          {title && <Heading style={{ margin: 0, fontSize: 'var(--fs-18)', fontWeight: 600 }}>{title}</Heading>}
          {headerSlot}
        </div>
      )}
      <div className="card__body" style={padding != null ? { padding } : undefined}>
        {children}
      </div>
      {footerSlot && (
        <div className="card__header" style={{ borderTop: '1px solid var(--color-line)', borderBottom: 0 }}>
          {footerSlot}
        </div>
      )}
    </section>
  );
}
