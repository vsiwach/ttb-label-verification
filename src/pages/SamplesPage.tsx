import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { fetchAllSamples, type SampleSummary } from '../api/samples';
import { API_BASE_URL } from '../api/client';
import Alert from '../components/Alert';
import Button from '../components/Button';
import { SkeletonBlock } from '../components/Skeleton';
import { IconArrowR, IconCheck, IconInfo } from '../components/icons';

const VERDICT_TINT: Record<string, { bg: string; fg: string; label: string }> = {
  'auto-pass':     { bg: 'var(--status-match-bg)',  fg: 'var(--status-match-fg)',  label: 'auto-pass' },
  'needs-confirm': { bg: 'var(--status-likely-bg)', fg: 'var(--status-likely-fg)', label: 'needs-confirm' },
  'needs-review':  { bg: 'var(--status-flag-bg)',   fg: 'var(--status-flag-fg)',   label: 'needs-review' },
};

const KIND_LABEL: Record<string, string> = {
  'real':      'COLA Cloud',
  'ttb-live':  'TTB Public Registry',
  'synthetic': 'Synthetic fixture',
};

type Filter = 'all' | SampleSummary['kind'] | SampleSummary['expectedOutcome'];

export default function SamplesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // When the user came from /batch ("Browse sample labels"), each card
  // becomes a toggle, a sticky header counts the selection, and a
  // "Queue N for batch" button rolls them back to /batch?samples=…
  // In single-label mode (default), cards are plain Links to /upload.
  const forBatch = searchParams.get('for') === 'batch';

  const [samples, setSamples]     = useState<SampleSummary[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [query, setQuery]         = useState('');
  const [filter, setFilter]       = useState<Filter>('all');
  const [selected, setSelected]   = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchAllSamples()
      .then(setSamples)
      .catch(err => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  function toggleSelected(id: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function queueForBatch() {
    if (selected.size === 0) return;
    const ids = Array.from(selected).join(',');
    navigate(`/batch?samples=${encodeURIComponent(ids)}`);
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return samples.filter(s => {
      if (filter !== 'all' && s.kind !== filter && s.expectedOutcome !== filter) return false;
      if (!q) return true;
      const hay = [
        s.applicationData.brandName,
        s.applicationData.classType,
        s.applicationData.beverageType,
        s.applicationData.countryOfOrigin || '',
        s.applicationData.colaNumber || '',
        s.id,
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [samples, query, filter]);

  const counts = useMemo(() => {
    const c = { all: samples.length, real: 0, 'ttb-live': 0, synthetic: 0,
                'auto-pass': 0, 'needs-confirm': 0, 'needs-review': 0 };
    for (const s of samples) {
      c[s.kind] += 1;
      c[s.expectedOutcome] += 1;
    }
    return c;
  }, [samples]);

  return (
    <div className="container">
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 16, flexWrap: 'wrap', marginBottom: 8,
        // Keep the action buttons reachable as the user scrolls through
        // a long gallery — sticky so "Queue N for batch" stays in view.
        position: forBatch ? 'sticky' : 'static',
        top: forBatch ? 0 : undefined,
        background: 'var(--color-bg)',
        paddingTop: forBatch ? 12 : 0,
        paddingBottom: forBatch ? 12 : 0,
        zIndex: forBatch ? 5 : undefined,
        borderBottom: forBatch ? '1px solid var(--color-line)' : undefined,
      }}>
        <h1 style={{ margin: 0 }}>{forBatch ? 'Pick labels for batch' : 'Sample directory'}</h1>
        {forBatch && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
            <span style={{ fontSize: 'var(--fs-16)', color: 'var(--color-ink-muted)' }}>
              <strong style={{ color: 'var(--color-ink)' }}>{selected.size}</strong>{' '}
              selected
            </span>
            <Button
              variant="ghost"
              onClick={() => navigate('/batch')}
              style={{ minHeight: 36 }}
            >Cancel</Button>
            <Button
              disabled={selected.size === 0}
              trailingIcon={IconArrowR}
              onClick={queueForBatch}
              style={{ minHeight: 36, minWidth: 180 }}
            >Queue {selected.size || ''} for batch</Button>
          </div>
        )}
      </div>
      <p style={{ fontSize: 'var(--fs-18)', color: 'var(--color-ink-muted)', marginBottom: 12, maxWidth: 'none' }}>
        {forBatch
          ? 'Tap any label to add it to the batch queue. Hit "Queue for batch" up top when you\'re done.'
          : 'Every label paired with TTB application data we can demo against — COLA Cloud free sample, the TTB Public Registry scrape, and the synthetic CI fixtures. Click any card to load it into the verify form, where you can edit ABV / Net contents before submitting.'}
      </p>
      <p style={{ margin: '0 0 24px', fontSize: 13, color: 'var(--color-ink-subtle)',
                  display: 'flex', alignItems: 'center', gap: 8 }}>
        <IconInfo size={14} aria-hidden="true" />
        The verdict pill is the engine's typical output on this label.
        Modal+Qwen extraction is non-deterministic, so a run may land one
        bucket above or below the pill.
      </p>

      {error && (
        <Alert variant="error" title="Couldn't load samples">{error}</Alert>
      )}

      {!error && (
        <div style={{
          display: 'flex', gap: 12, alignItems: 'center',
          marginBottom: 20, flexWrap: 'wrap',
        }}>
          <input
            type="search"
            placeholder="Search brand, class, country, COLA #…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            style={{
              flex: '1 1 280px', minWidth: 0,
              padding: '10px 12px', fontSize: 14,
              border: '1px solid var(--color-line-strong)', borderRadius: 4,
              background: '#fff',
            }}
          />
          <div role="tablist" style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {([
              ['all',           `All (${counts.all})`],
              ['real',          `COLA Cloud (${counts.real})`],
              ['ttb-live',      `TTB Registry (${counts['ttb-live']})`],
              ['synthetic',     `Synthetic (${counts.synthetic})`],
              ['auto-pass',     `Auto-pass (${counts['auto-pass']})`],
              ['needs-review',  `Review (${counts['needs-review']})`],
            ] as const).map(([k, label]) => (
              <button
                key={k}
                type="button"
                onClick={() => setFilter(k as Filter)}
                style={{
                  padding: '6px 10px', fontSize: 12, fontWeight: 600,
                  border: '1px solid ' + (filter === k ? 'var(--color-primary)' : 'var(--color-line-strong)'),
                  background: filter === k ? 'var(--color-primary)' : '#fff',
                  color: filter === k ? '#fff' : 'var(--color-ink)',
                  borderRadius: 4, cursor: 'pointer', minHeight: 32,
                }}
              >{label}</button>
            ))}
          </div>
        </div>
      )}

      {loading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonBlock key={i} height={280} style={{ borderRadius: 6 }} />
          ))}
        </div>
      )}

      {!loading && !error && (
        <>
          <p style={{ margin: '0 0 12px', color: 'var(--color-ink-subtle)', fontSize: 13 }}>
            Showing {filtered.length} of {samples.length} samples.
            {forBatch && selected.size > 0 && <>  ·  <strong>{selected.size} selected</strong></>}
          </p>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
            gap: 16,
            paddingBottom: 40,
          }}>
            {filtered.map(s => (
              <SampleCard
                key={s.id}
                sample={s}
                forBatch={forBatch}
                isSelected={selected.has(s.id)}
                onToggle={forBatch ? () => toggleSelected(s.id) : undefined}
              />
            ))}
          </div>
          {filtered.length === 0 && (
            <p style={{ color: 'var(--color-ink-muted)', textAlign: 'center', padding: 40 }}>
              No samples match that filter.
            </p>
          )}
        </>
      )}

    </div>
  );
}

interface SampleCardProps {
  sample: SampleSummary;
  forBatch?: boolean;
  isSelected?: boolean;
  onToggle?: () => void;
}

function SampleCard({ sample, forBatch, isSelected, onToggle }: SampleCardProps) {
  const tint = VERDICT_TINT[sample.expectedOutcome] || VERDICT_TINT['auto-pass'];
  const base = API_BASE_URL.replace(/\/api$/, '');
  const imgSrc = `${base}${sample.imageUrl}`;

  const cardStyle: React.CSSProperties = {
    display: 'flex', flexDirection: 'column',
    padding: 0, overflow: 'hidden',
    textDecoration: 'none', color: 'inherit',
    border: '1px solid ' + (isSelected ? 'var(--color-primary)' : 'var(--color-line)'),
    transition: 'border-color 120ms, box-shadow 120ms',
    boxShadow: isSelected ? '0 0 0 2px var(--color-primary-tint, rgba(0,102,179,0.18))' : 'none',
    position: 'relative',
    cursor: 'pointer',
  };

  const cardContent = (
    <>
      <div style={{
        width: '100%', aspectRatio: '3 / 4',
        background: '#f5f5f5',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        overflow: 'hidden', borderBottom: '1px solid var(--color-line)',
      }}>
        <img
          src={imgSrc}
          alt={`Label artwork for ${sample.applicationData.brandName}`}
          loading="lazy"
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        />
      </div>
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
          <div style={{ minWidth: 0 }}>
            <strong style={{
              fontSize: 'var(--fs-16)', lineHeight: 1.3,
              overflow: 'hidden', display: '-webkit-box',
              WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
            }}>{sample.applicationData.brandName || '(no brand)'}</strong>
            {sample.applicationData.productName && (
              <p style={{
                margin: '2px 0 0', fontSize: 13, fontWeight: 500,
                color: 'var(--color-ink-muted)', fontStyle: 'italic',
                overflow: 'hidden', display: '-webkit-box',
                WebkitLineClamp: 1, WebkitBoxOrient: 'vertical',
              }}>{sample.applicationData.productName}</p>
            )}
          </div>
          <span style={{
            fontSize: 11, padding: '2px 6px', borderRadius: 999,
            background: tint.bg, color: tint.fg, fontWeight: 600,
            textTransform: 'lowercase', flexShrink: 0, whiteSpace: 'nowrap',
          }}>{tint.label}</span>
        </div>
        <p style={{
          margin: 0, fontSize: 13, color: 'var(--color-ink-muted)',
          overflow: 'hidden', display: '-webkit-box',
          WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
        }}>{sample.applicationData.classType || '(no class)'}</p>
        <div style={{
          display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
          fontSize: 11, color: 'var(--color-ink-subtle)',
        }}>
          <span style={{
            padding: '2px 6px', borderRadius: 3,
            background: 'var(--color-bg-subtle)', textTransform: 'capitalize',
          }}>{sample.applicationData.beverageType}</span>
          <span style={{
            padding: '2px 6px', borderRadius: 3,
            background: 'var(--color-bg-subtle)',
          }}>{KIND_LABEL[sample.kind] || sample.kind}</span>
        </div>
        <span style={{
          marginTop: 4, display: 'inline-flex', alignItems: 'center', gap: 4,
          color: 'var(--color-primary)', fontWeight: 600, fontSize: 13,
        }}>
          {forBatch
            ? (isSelected
                ? <><IconCheck size={14} aria-hidden="true" /> Selected</>
                : <>Tap to select <IconArrowR size={14} aria-hidden="true" /></>)
            : <>Use this sample <IconArrowR size={14} aria-hidden="true" /></>}
        </span>
      </div>
    </>
  );

  if (forBatch) {
    return (
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={isSelected}
        className="card"
        style={{ ...cardStyle, textAlign: 'left', background: '#fff', font: 'inherit' }}
      >
        {isSelected && (
          <span aria-hidden="true" style={{
            position: 'absolute', top: 8, right: 8, zIndex: 1,
            width: 24, height: 24, borderRadius: '50%',
            background: 'var(--color-primary)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <IconCheck size={14} />
          </span>
        )}
        {cardContent}
      </button>
    );
  }

  return (
    <Link
      to={`/upload?sample=${encodeURIComponent(sample.id)}`}
      className="card"
      style={cardStyle}
      onMouseEnter={e => {
        (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-primary)';
        (e.currentTarget as HTMLElement).style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)';
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-line)';
        (e.currentTarget as HTMLElement).style.boxShadow = 'none';
      }}
    >
      {cardContent}
    </Link>
  );
}
