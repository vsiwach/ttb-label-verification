import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { ImageQuality, VerificationField } from '../api/types';
import { verifyLabel } from '../api/client';
import { verifyStore, useVerifyStore, type UploadedImage } from '../store/verifyStore';
import Alert from '../components/Alert';
import Button from '../components/Button';
import Card from '../components/Card';
import DecisionPanel from '../components/DecisionPanel';
import GovernmentWarningPanel from '../components/GovernmentWarningPanel';
import StatusBadge from '../components/StatusBadge';
import { SkeletonLine } from '../components/Skeleton';
import { IconArrowL, IconCheck, IconChevronR, IconFlag, IconWarn } from '../components/icons';
import { formatBytes } from '../utils/downscaleImage';

const EXPECTED_FIELDS = [
  { key: 'brandName',          name: 'Brand name' },
  { key: 'classType',          name: 'Class & type' },
  { key: 'alcoholContent',     name: 'Alcohol content' },
  { key: 'netContents',        name: 'Net contents' },
  { key: 'bottlerNameAddress', name: 'Bottler name/address' },
  { key: 'countryOfOrigin',    name: 'Country of origin' },
];

const STATUS_ORDER: Record<string, number> = { flag: 0, likely: 1, match: 2 };

type LiveField = VerificationField & { _wasConfirmed?: boolean };

function statusCounts(fields: VerificationField[]) {
  return fields.reduce<Record<'match' | 'likely' | 'flag', number>>(
    (a, f) => (a[f.status] = (a[f.status] || 0) + 1, a),
    { match: 0, likely: 0, flag: 0 },
  );
}

export default function ResultPage() {
  const navigate = useNavigate();
  const state = useVerifyStore();
  const { image, applicationData, status, result, error } = state;

  const expected = useMemo(() => {
    if (!applicationData) return [];
    return EXPECTED_FIELDS
      .filter(f => f.key !== 'countryOfOrigin' || !!applicationData.countryOfOrigin)
      .map(f => f.name);
  }, [applicationData]);

  const startedRef = useRef(false);
  useEffect(() => {
    if (!applicationData) return;
    if (startedRef.current) return;
    // Skip the verify call entirely when the store already carries a
    // finished result — this happens when /batch opens a per-item view:
    // the batch endpoint produced the VerificationResult upstream and
    // BatchPage.openItem hands it through. Re-firing /api/verify in
    // that case would hit a 422 because the batch's UploadedImage
    // carries blob=null (only a data URL for thumbnail rendering).
    if (status === 'done' && result.fields.length > 0) {
      startedRef.current = true;
      return;
    }
    startedRef.current = true;
    verifyStore.setState({
      status: 'streaming',
      result: { fields: [], governmentWarning: null, imageQuality: null, timing: null },
      error: null,
    });
    verifyLabel(
      image?.blob ?? null,
      applicationData,
      (field) => {
        verifyStore.setState(s => ({
          ...s,
          result: { ...s.result, fields: [...s.result.fields, field] },
        }));
      },
      {
        onGovernmentWarning: (gw) => verifyStore.setState(s => ({ ...s, result: { ...s.result, governmentWarning: gw } })),
        onImageQuality:      (iq) => verifyStore.setState(s => ({ ...s, result: { ...s.result, imageQuality: iq } })),
      },
    )
      .then((full) => verifyStore.setState(s => ({
        ...s,
        status: 'done',
        result: { ...s.result, timing: full.timing ?? null },
      })))
      .catch((err) => verifyStore.setState({ status: 'error', error: err instanceof Error ? err : new Error(String(err)) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationData, image]);

  useEffect(() => {
    if (status === 'idle' && !applicationData) startedRef.current = false;
  }, [status, applicationData]);

  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [liveMessage, setLiveMessage] = useState('');

  const fields: LiveField[] = useMemo(
    () => result.fields.map(f => confirmed[f.fieldName] ? { ...f, status: 'match' as const, _wasConfirmed: true } : f),
    [result.fields, confirmed],
  );

  const counts = statusCounts(fields);
  const totalExpected = expected.length || 5;
  const totalArrived = result.fields.length;
  const isStreaming  = status === 'streaming';
  const isDone       = status === 'done';

  useEffect(() => {
    if (!isStreaming) return;
    setLiveMessage(`Verifying. ${totalArrived} of ${totalExpected} fields checked.`);
  }, [totalArrived, totalExpected, isStreaming]);
  useEffect(() => {
    if (isDone) setLiveMessage(`Verification complete. ${counts.match} match, ${counts.likely} likely, ${counts.flag} flag.`);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDone]);

  const confirmField = (name: string) => {
    setConfirmed(prev => ({ ...prev, [name]: true }));
    setLiveMessage(`${name} confirmed. Status changed to Match.`);
  };

  const sortedFields = useMemo(
    () => [...fields].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]),
    [fields],
  );

  if (!applicationData) {
    return (
      <div className="container container--narrow" style={{ paddingTop: 40 }}>
        <Card>
          <h1 style={{ marginBottom: 8 }}>Nothing to verify yet</h1>
          <p style={{ color: 'var(--color-ink-muted)' }}>
            Upload a label image and enter the application data first.
          </p>
          <Button icon={IconArrowL} onClick={() => navigate('/upload')}>Go to upload</Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="container">
      <Link
        to="/upload"
        onClick={() => { verifyStore.reset(); startedRef.current = false; }}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 16, fontWeight: 600 }}
      >
        <IconArrowL size={16} /> Back to upload
      </Link>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 24, flexWrap: 'wrap', marginBottom: 8 }}>
        <div>
          <p style={{ marginBottom: 4 }}><span className="tag">Step 2 of 2</span></p>
          <h1 style={{ margin: 0 }}>{applicationData.brandName || 'Verification result'}</h1>
        </div>
        <div style={{ color: 'var(--color-ink-muted)', fontSize: 14 }}>
          {applicationData.colaNumber && <>COLA #{applicationData.colaNumber} · </>}
          <span style={{ textTransform: 'capitalize' }}>{applicationData.beverageType}</span>
          {applicationData.classType && <> · {applicationData.classType}</>}
        </div>
      </div>

      {result.timing && !error && <LatencyBadge timing={result.timing} />}

      <p className="sr-only" role="status" aria-live="polite">{liveMessage}</p>

      {!error && (
        <SummaryBar counts={counts} isStreaming={isStreaming} totalArrived={totalArrived} totalExpected={totalExpected} />
      )}

      {error && (
        <div style={{ marginTop: 16 }}>
          <Alert variant="error" title="Verification failed">
            <p>{error.message}</p>
          </Alert>
        </div>
      )}

      <div className="result-grid" style={{ marginTop: 24 }}>
        <aside aria-label="Uploaded label">
          <LabelImagePanel image={image} imageQuality={result.imageQuality} isDone={isDone} />
        </aside>

        <section aria-labelledby="fields-h">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
            <h2 id="fields-h" style={{ margin: 0, fontSize: 'var(--fs-24)' }}>Field verification</h2>
            <span style={{ color: 'var(--color-ink-muted)', fontSize: 14 }} aria-hidden="true">
              {isStreaming
                ? `Verifying… ${totalArrived} of ${totalExpected} fields checked`
                : `${totalArrived} of ${totalArrived} fields checked`}
            </span>
          </div>

          <div className="card card--flush" style={{ overflow: 'visible' }}>
            {sortedFields.map(f => (
              <ResultFieldRow key={f.fieldName} field={f} onConfirm={() => confirmField(f.fieldName)} />
            ))}
            {isStreaming && Array.from({ length: Math.max(0, totalExpected - totalArrived) }).map((_, i) => (
              <SkeletonRow key={`sk-${i}`} />
            ))}
          </div>

          {(isStreaming || result.governmentWarning) && (
            <GovernmentWarningPanel
              gw={result.governmentWarning}
              loading={!result.governmentWarning && isStreaming}
            />
          )}

          {result.governmentWarning && result.imageQuality && (
            <DecisionPanel
              result={{
                fields: result.fields,
                governmentWarning: result.governmentWarning,
                imageQuality: result.imageQuality,
              }}
              applicationData={applicationData}
              streamingDone={isDone}
            />
          )}
        </section>
      </div>
    </div>
  );
}

function SummaryBar({ counts, isStreaming, totalArrived, totalExpected }: {
  counts: { match: number; likely: number; flag: number };
  isStreaming: boolean;
  totalArrived: number;
  totalExpected: number;
}) {
  const { match, likely, flag } = counts;
  let title: string;
  let sub: string;
  let variant: 'match' | 'likely' | 'flag';
  if (flag > 0) {
    variant = 'flag';
    title = `${flag} flag${flag === 1 ? '' : 's'} need${flag === 1 ? 's' : ''} review before you can approve`;
    sub = `${match} match · ${likely} likely · ${flag} flag · ${totalArrived} of ${totalExpected} fields checked`;
  } else if (likely > 0) {
    variant = 'likely';
    title = `${likely} likely match${likely === 1 ? '' : 'es'} — confirm to approve`;
    sub = `${match} match · ${likely} likely · 0 flag · ${totalArrived} of ${totalExpected} fields checked`;
  } else if (isStreaming) {
    variant = 'match';
    title = `Verifying… ${totalArrived} of ${totalExpected} fields checked`;
    sub = 'Results stream in as they finish.';
  } else {
    variant = 'match';
    title = `All ${match} fields match`;
    sub = 'Ready to approve. No agent action required (pending Government Warning audit in the next step).';
  }
  const Icon = variant === 'match' ? IconCheck : variant === 'likely' ? IconWarn : IconFlag;
  return (
    <div className={`verdict verdict--${variant}`} style={{ marginTop: 16 }} aria-live="polite">
      <span className="verdict__icon" aria-hidden="true">
        <Icon size={20} strokeWidth={2.5} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p className="verdict__title">{title}</p>
        <p className="verdict__sub">{sub}</p>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        {match  > 0 && <StatusBadge status="match" />}
        {likely > 0 && <StatusBadge status="likely" />}
        {flag   > 0 && <StatusBadge status="flag" />}
      </div>
    </div>
  );
}

function LabelImagePanel({ image, imageQuality, isDone }: {
  image: UploadedImage | null;
  imageQuality: ImageQuality | null;
  isDone: boolean;
}) {
  const [zoomed, setZoomed] = useState(false);
  // Esc closes the lightbox so an agent who clicked into it can dismiss
  // without reaching for the mouse — speeds up the "open, eyeball the
  // side-panel text, decide" flow on labels with tiny imported-by /
  // country-of-origin text.
  useEffect(() => {
    if (!zoomed) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setZoomed(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [zoomed]);

  return (
    <div>
      <div className="card card--flush" style={{ overflow: 'hidden' }}>
        {image ? (
          <button
            type="button"
            onClick={() => setZoomed(true)}
            aria-label="Open larger view of the label image"
            style={{
              display: 'block', width: '100%',
              padding: 0, border: 0, background: '#f5f5f5',
              cursor: 'zoom-in', position: 'relative',
            }}
          >
            <img
              src={image.dataUrl}
              alt={`Uploaded label — ${image.fileName} (click to enlarge)`}
              style={{ display: 'block', width: '100%', height: 'auto', maxHeight: 520, objectFit: 'contain', background: '#f5f5f5' }}
            />
            <span style={{
              position: 'absolute', bottom: 8, right: 8,
              padding: '4px 8px', fontSize: 11, fontWeight: 600,
              background: 'rgba(0,0,0,0.6)', color: '#fff', borderRadius: 4,
              pointerEvents: 'none',
            }}>Click to enlarge</span>
          </button>
        ) : (
          <div style={{
            aspectRatio: '3/4',
            background: 'repeating-linear-gradient(135deg, #f1f1f1 0 12px, #fafafa 12px 24px)',
            display: 'grid', placeItems: 'center',
            color: 'var(--color-ink-subtle)', fontFamily: 'var(--font-mono)', fontSize: 13,
          }}>no image</div>
        )}
        {image && (
          <div className="card__header" style={{ borderBottom: 0, borderTop: '1px solid var(--color-line)' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{image.fileName}</div>
              <div style={{ color: 'var(--color-ink-muted)', fontSize: 13 }}>
                {image.originalWidth}×{image.originalHeight} → {image.width}×{image.height} · {formatBytes(image.optimizedSize)}
              </div>
            </div>
          </div>
        )}
      </div>
      <ImageQualityMeter quality={imageQuality} loading={!imageQuality && !isDone} />
      {zoomed && image && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Enlarged label image"
          onClick={() => setZoomed(false)}
          style={{
            position: 'fixed', inset: 0, zIndex: 100,
            background: 'rgba(0,0,0,0.85)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 24, cursor: 'zoom-out',
          }}
        >
          <img
            src={image.dataUrl}
            alt={image.fileName}
            style={{
              maxWidth: '95vw', maxHeight: '95vh',
              objectFit: 'contain',
              background: '#fff', borderRadius: 4,
              boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
            }}
          />
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setZoomed(false); }}
            aria-label="Close enlarged view"
            style={{
              position: 'absolute', top: 16, right: 16,
              padding: '8px 16px', fontSize: 14, fontWeight: 600,
              background: '#fff', color: 'var(--color-ink)',
              border: 'none', borderRadius: 4, cursor: 'pointer',
            }}
          >Close ✕</button>
        </div>
      )}
    </div>
  );
}

function ImageQualityMeter({ quality, loading }: { quality: ImageQuality | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="card" style={{ marginTop: 16, padding: 16 }} aria-busy="true">
        <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--color-ink-muted)', marginBottom: 8 }}>
          Image quality
        </div>
        <SkeletonLine width="60%" />
        <div style={{ height: 8 }} />
        <SkeletonLine width="100%" height={10} />
      </div>
    );
  }
  if (!quality) return null;
  const pct = Math.round(quality.score * 100);
  const legible = quality.legible;
  const tone = legible && pct >= 80 ? 'match' : legible ? 'likely' : 'flag';
  const Icon = tone === 'match' ? IconCheck : tone === 'likely' ? IconWarn : IconFlag;
  return (
    <div className="card" style={{ marginTop: 16, padding: 16 }}>
      <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--color-ink-muted)', marginBottom: 8 }}>
        Image quality
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{
          width: 22, height: 22, borderRadius: 999,
          background: `var(--status-${tone}-fg)`, color: '#fff',
          display: 'grid', placeItems: 'center', flexShrink: 0,
        }} aria-hidden="true">
          <Icon size={13} strokeWidth={3} />
        </span>
        <span style={{ fontSize: 'var(--fs-18)', fontWeight: 700 }}>{pct}%</span>
        <span style={{ color: 'var(--color-ink-muted)' }}>— {legible ? 'Legible' : 'Not legible'}</span>
      </div>
      <div
        style={{ position: 'relative', height: 10, borderRadius: 6, background: 'var(--color-bg-alt)', overflow: 'hidden' }}
        role="meter"
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
        aria-valuetext={`${pct}%, ${legible ? 'legible' : 'not legible'}`}
      >
        <div style={{ position: 'absolute', inset: 0, width: `${pct}%`, background: `var(--status-${tone}-fg)` }} />
      </div>
      {quality.note && <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--color-ink-muted)' }}>{quality.note}</p>}
      {!legible && (
        <div style={{ marginTop: 12 }}>
          <Alert variant="error" title="Re-upload a sharper image">
            <p>The OCR signal is too weak to make a confident verdict. Ask the applicant for a higher-resolution scan.</p>
          </Alert>
        </div>
      )}
    </div>
  );
}

function ResultFieldRow({ field, onConfirm }: { field: LiveField; onConfirm: () => void }) {
  const [open, setOpen] = useState(false);
  const evidenceId = `evid-${field.fieldName.replace(/\W+/g, '-').toLowerCase()}`;

  return (
    <div
      className="result-row"
      data-status={field.status}
      data-confirmed={field._wasConfirmed ? 'true' : undefined}
    >
      <div style={{ padding: '16px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
          <div style={{ minWidth: 0, flex: '1 1 200px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--color-ink-muted)' }}>
              {field.fieldName}
            </div>
            {field.regulationCite && (
              <div style={{ fontSize: 12, color: 'var(--color-ink-subtle)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                {field.regulationCite}
              </div>
            )}
          </div>
          <StatusBadge status={field.status} />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {field.status === 'likely' && !field._wasConfirmed && (
              <Button variant="secondary" icon={IconCheck} onClick={onConfirm}>Confirm</Button>
            )}
            {field.evidenceCropUrl && (
              <button
                type="button"
                className="btn btn--ghost"
                aria-expanded={open}
                aria-controls={evidenceId}
                onClick={() => setOpen(o => !o)}
              >
                {open ? 'Hide evidence' : 'Show evidence'}
                <span aria-hidden="true" style={{
                  display: 'inline-block', marginLeft: 4,
                  transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
                  transition: 'transform 160ms',
                }}>
                  <IconChevronR size={16} />
                </span>
              </button>
            )}
          </div>
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 16,
        }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--color-ink-muted)', marginBottom: 2 }}>Declared</div>
            <div style={{ fontWeight: 600, wordBreak: 'break-word' }}>{field.declaredValue}</div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--color-ink-muted)', marginBottom: 2 }}>Extracted</div>
            <div style={{ fontWeight: 600, wordBreak: 'break-word' }}>{field.extractedValue}</div>
            {field.note && (
              <div style={{ fontSize: 13, color: 'var(--color-ink-muted)', marginTop: 4 }}>{field.note}</div>
            )}
          </div>
        </div>
      </div>

      {field.evidenceCropUrl && (
        <div
          id={evidenceId}
          hidden={!open}
          style={{
            background: 'var(--color-bg-alt)',
            borderTop: open ? '1px solid var(--color-line)' : 'none',
            padding: open ? '16px 24px' : 0,
            display: open ? 'flex' : 'none',
            gap: 16, alignItems: 'flex-start', flexWrap: 'wrap',
          }}
        >
          <img
            src={field.evidenceCropUrl}
            alt={`Evidence crop for ${field.fieldName}`}
            style={{
              width: 220, maxWidth: '100%', height: 'auto', borderRadius: 4,
              border: '1px solid var(--color-line)', background: '#fff',
            }}
          />
          <div style={{ flex: '1 1 240px', minWidth: 0 }}>
            <p style={{ margin: 0, fontWeight: 600 }}>Evidence region</p>
            <p style={{ margin: '4px 0 0', color: 'var(--color-ink-muted)', fontSize: 14 }}>
              This is the cropped portion of the label the AI used to read <em>{field.fieldName.toLowerCase()}</em>.
              {field.regulationCite && <> Compared against <code>{field.regulationCite}</code>.</>}
              {' '}Confidence: <strong>{Math.round((field.confidence || 0) * 100)}%</strong>.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function SkeletonRow() {
  return (
    <div aria-hidden="true" style={{ padding: '16px 24px', borderTop: '1px solid var(--color-line)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
        <div style={{ flex: '1 1 200px' }}>
          <SkeletonLine width="50%" height={10} />
        </div>
        <SkeletonLine width={140} height={26} style={{ borderRadius: 999 }} />
        <SkeletonLine width={120} height={36} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
        <div>
          <SkeletonLine width="35%" height={10} />
          <div style={{ height: 6 }} />
          <SkeletonLine width="75%" />
        </div>
        <div>
          <SkeletonLine width="35%" height={10} />
          <div style={{ height: 6 }} />
          <SkeletonLine width="75%" />
        </div>
      </div>
    </div>
  );
}

const MODE_LABEL: Record<string, { name: string; tone: 'dev' | 'prod' }> = {
  'claude-code': { name: 'Claude Code CLI (local dev)',          tone: 'dev'  },
  cloud:         { name: 'Claude API (paid)',                    tone: 'dev'  },
  modal:         { name: 'Modal · Qwen2.5-VL LoRA (deployed)',   tone: 'prod' },
  sft:           { name: 'Qwen2.5-VL LoRA (local GPU)',          tone: 'prod' },
  onprem:        { name: 'On-prem VLM',                          tone: 'prod' },
  mock:          { name: 'Mock (test fixture)',                  tone: 'dev'  },
};

function LatencyBadge({ timing }: { timing: { inferenceMode: string; extractorMs: number; rulesMs: number; totalMs: number } }) {
  const meta = MODE_LABEL[timing.inferenceMode] || { name: timing.inferenceMode, tone: 'dev' as const };
  const formatMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms} ms`);
  const isProd = meta.tone === 'prod';
  return (
    <div
      aria-label="Inference timing"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 10,
        padding: '6px 12px', marginTop: 8,
        borderRadius: 999, fontSize: 13,
        background: isProd ? 'var(--status-match-bg)' : 'var(--status-info-bg, #eef1f7)',
        color:      isProd ? 'var(--status-match-fg)' : 'var(--status-info-fg, #1a4480)',
        border: '1px solid ' + (isProd ? 'var(--status-match-border)' : 'var(--color-line)'),
      }}
    >
      <span style={{ fontWeight: 700 }}>{formatMs(timing.totalMs)}</span>
      <span style={{ opacity: 0.7 }}>·</span>
      <span>{meta.name}</span>
      <span style={{ opacity: 0.7 }}>·</span>
      <span style={{ opacity: 0.85 }} title="extractor / rules engine">
        extractor {formatMs(timing.extractorMs)} + rules {formatMs(timing.rulesMs)}
      </span>
    </div>
  );
}
