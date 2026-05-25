import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { ApplicationData, BatchItemResult, VerificationField } from '../api/types';
import { verifyBatch } from '../api/client';
import { SAMPLE_APPLICATIONS as SAVED_APPLICATIONS } from '../api/sampleApplications';
import { verifyStore, type UploadedImage } from '../store/verifyStore';
import Alert from '../components/Alert';
import Button from '../components/Button';
import FileDropzone from '../components/FileDropzone';
import StatusBadge from '../components/StatusBadge';
import {
  IconArrowL, IconArrowR, IconCheck, IconChevronR, IconClock,
  IconFlag, IconFolder, IconWarn,
} from '../components/icons';
import { formatBytes } from '../utils/downscaleImage';

type GroupKey = BatchItemResult['group'];
type FilterKey = 'all' | 'review' | 'confirm' | 'pass';

const GROUP_META: Record<GroupKey, { label: string; tone: 'flag' | 'likely' | 'match'; Icon: typeof IconCheck; desc: string }> = {
  'needs-review':  { label: 'Needs review',  tone: 'flag',   Icon: IconFlag,  desc: 'Has a flagged field or a Government Warning failure.' },
  'needs-confirm': { label: 'Needs confirm', tone: 'likely', Icon: IconWarn,  desc: 'Has at least one likely-match field — a one-click Confirm resolves it.' },
  'auto-pass':     { label: 'Auto-pass',     tone: 'match',  Icon: IconCheck, desc: 'All fields match and the Government Warning is compliant.' },
};

const FILTER_TO_GROUP: Record<Exclude<FilterKey, 'all'>, GroupKey> = {
  review: 'needs-review',
  confirm: 'needs-confirm',
  pass: 'auto-pass',
};

function quickSummary(item: BatchItemResult): string {
  const fr = item.result.fields;
  const flag = fr.find(f => f.status === 'flag');
  if (flag) return `${flag.fieldName} mismatch — "${flag.declaredValue}" vs "${flag.extractedValue}"`;
  const gw = item.result.governmentWarning;
  if (gw && !gw.verbatimMatch) return 'Government Warning: wording or styling differs from required.';
  const likely = fr.find(f => f.status === 'likely');
  if (likely) return `${likely.fieldName}: ${likely.note || 'one-click confirm'}`;
  return 'All checks passed.';
}

function groupCounts(items: BatchItemResult[]): Record<GroupKey, number> {
  const c: Record<GroupKey, number> = { 'needs-review': 0, 'needs-confirm': 0, 'auto-pass': 0 };
  for (const it of items) c[it.group] += 1;
  return c;
}

type QueuedFile = File;

function guessAppDataFor(item: BatchItemResult): ApplicationData {
  const f = (item.fileName || '').toLowerCase();
  if (f.includes('stone'))     return SAVED_APPLICATIONS[1];
  if (f.includes('northwind')) return SAVED_APPLICATIONS[2];
  return SAVED_APPLICATIONS[0];
}

// ─────────────────────────────────────────────────────────────────────────────
export default function BatchPage() {
  const navigate = useNavigate();
  const [phase, setPhase]   = useState<'upload' | 'processing' | 'done'>('upload');
  const [files, setFiles]   = useState<QueuedFile[]>([]);
  const [items, setItems]   = useState<BatchItemResult[]>([]);
  const [shared, setShared] = useState<ApplicationData | null>(null);
  const [filter, setFilter] = useState<FilterKey>('all');
  // Auto-pass items still need agent confirmation — open by default so the
  // agent sees every item and isn't tempted to skip a bucket.
  const [autoPassOpen, setAutoPassOpen] = useState(true);

  function handleFiles(list: File[]) { setFiles(prev => [...prev, ...list]); }
  function clearFiles() { setFiles([]); setItems([]); setPhase('upload'); }

  async function startProcessing() {
    if (files.length === 0) return;
    setPhase('processing');
    setItems([]);
    await verifyBatch(files, shared ?? undefined, (item) => {
      setItems(prev => [...prev, item]);
    });
    setPhase('done');
  }

  function openItem(item: BatchItemResult) {
    verifyStore.reset();
    const image: UploadedImage = {
      blob: null,
      dataUrl: item.thumbnailUrl,
      fileName: item.fileName,
      width: 0, height: 0,
      originalWidth: 0, originalHeight: 0,
      originalSize: 0, optimizedSize: 0,
    };
    verifyStore.setState({
      image,
      applicationData: shared ?? guessAppDataFor(item),
    });
    navigate('/result');
  }

  function startReview() {
    const queue = items.filter(it => it.group !== 'auto-pass');
    verifyStore.setState({ reviewSession: { queue, shared, startedAt: Date.now() } });
    navigate('/review');
  }

  return (
    <div className="container">
      <Link
        to="/upload"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 16, fontWeight: 600 }}
      >
        <IconArrowL size={16} /> Single-label upload
      </Link>

      <p style={{ marginBottom: 8 }}><span className="tag">Bulk review</span></p>
      <h1 style={{ marginBottom: 8 }}>Review a batch</h1>
      <p style={{ fontSize: 'var(--fs-18)', color: 'var(--color-ink-muted)', maxWidth: 'none', marginBottom: 32 }}>
        Upload up to a few hundred labels. We process them in parallel and surface
        only the ones that need your attention — flags first, matches collapsed.
      </p>

      {phase === 'upload' && (
        <UploadPanel
          files={files}
          shared={shared}
          setShared={setShared}
          onFiles={handleFiles}
          onClear={clearFiles}
          onStart={startProcessing}
        />
      )}

      {phase !== 'upload' && (
        <Dashboard
          phase={phase}
          totalFiles={files.length}
          items={items}
          filter={filter}
          setFilter={setFilter}
          autoPassOpen={autoPassOpen}
          setAutoPassOpen={setAutoPassOpen}
          onOpenItem={openItem}
          onReset={clearFiles}
          onStartReview={startReview}
        />
      )}
    </div>
  );
}

interface UploadPanelProps {
  files: QueuedFile[];
  shared: ApplicationData | null;
  setShared: (a: ApplicationData | null) => void;
  onFiles: (files: File[]) => void;
  onClear: () => void;
  onStart: () => void;
}

function UploadPanel({ files, shared, setShared, onFiles, onClear, onStart }: UploadPanelProps) {
  const totalBytes = files.reduce((a, f) => a + ((f as File).size || 0), 0);
  const ready = files.length > 0;

  return (
    <>
      <FileDropzone
        accept="image/jpeg,image/png"
        multiple
        onFiles={onFiles}
        label="Drag a folder of label images"
        hint="JPEG or PNG, hundreds of files are fine."
        buttonLabel="Choose files…"
        icon={IconFolder}
      />

      <div style={{ marginTop: 24 }}>
        <h3 style={{ margin: '0 0 8px', fontSize: 'var(--fs-18)' }}>Optional: attach a shared application</h3>
        <p style={{ margin: '0 0 12px', color: 'var(--color-ink-muted)', fontSize: 14 }}>
          When all images belong to the same COLA submission. Otherwise leave it
          blank — every label is still audited for image-only checks (Government
          Warning, image quality).
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          {SAVED_APPLICATIONS.map(s => (
            <button
              key={s.colaNumber}
              type="button"
              className={`btn ${shared?.colaNumber === s.colaNumber ? 'btn--primary' : 'btn--secondary'}`}
              style={{ minHeight: 36, padding: '0 12px', fontSize: 14 }}
              onClick={() => setShared(shared?.colaNumber === s.colaNumber ? null : s)}
            >
              {shared?.colaNumber === s.colaNumber ? '✓ ' : ''}{s.brandName}
            </button>
          ))}
          {shared && <button type="button" className="btn btn--ghost" onClick={() => setShared(null)}>Clear</button>}
        </div>
      </div>

      <hr className="divider" style={{ marginTop: 32 }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <strong style={{ fontSize: 'var(--fs-20)' }}>
            {files.length === 0 ? 'No files queued' : `${files.length} file${files.length === 1 ? '' : 's'} queued`}
          </strong>
          {totalBytes > 0 && <span style={{ color: 'var(--color-ink-muted)', marginLeft: 8 }}>· {formatBytes(totalBytes)}</span>}
          {shared && (
            <p style={{ margin: '4px 0 0', color: 'var(--color-ink-muted)', fontSize: 14 }}>
              Shared application: <strong>{shared.brandName}</strong> · COLA {shared.colaNumber}
            </p>
          )}
        </div>
        {files.length > 0 && <Button variant="ghost" onClick={onClear}>Clear queue</Button>}
        <Button size="lg" disabled={!ready} trailingIcon={IconArrowR} onClick={onStart} style={{ minWidth: 220 }}>
          Process {files.length} {files.length === 1 ? 'label' : 'labels'}
        </Button>
      </div>
    </>
  );
}

interface DashboardProps {
  phase: 'processing' | 'done';
  totalFiles: number;
  items: BatchItemResult[];
  filter: FilterKey;
  setFilter: (f: FilterKey) => void;
  autoPassOpen: boolean;
  setAutoPassOpen: (fn: (o: boolean) => boolean) => void;
  onOpenItem: (item: BatchItemResult) => void;
  onReset: () => void;
  onStartReview: () => void;
}

function Dashboard({ phase, totalFiles, items, filter, setFilter, autoPassOpen, setAutoPassOpen, onOpenItem, onReset, onStartReview }: DashboardProps) {
  const done = items.length;
  const counts = groupCounts(items);
  const needsAction = counts['needs-review'] + counts['needs-confirm'];
  const processing  = phase === 'processing';

  const filtered = useMemo(() => {
    if (filter === 'all') return items;
    return items.filter(it => it.group === FILTER_TO_GROUP[filter]);
  }, [items, filter]);

  return (
    <>
      <div className="card" style={{ padding: 20, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: 8, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{
              width: 36, height: 36, borderRadius: 8,
              background: processing ? 'var(--color-primary-tint-2)' : 'var(--status-match-bg)',
              color: processing ? 'var(--color-primary)' : 'var(--status-match-fg)',
              display: 'grid', placeItems: 'center',
            }} aria-hidden="true">
              {processing ? <IconClock size={20} /> : <IconCheck size={20} strokeWidth={3} />}
            </span>
            <div>
              <strong style={{ fontSize: 'var(--fs-18)' }}>
                {processing
                  ? `Processing ${totalFiles} labels — ${done} done`
                  : `All ${totalFiles} labels processed`}
              </strong>
              <div style={{ color: 'var(--color-ink-muted)', fontSize: 14 }}>
                {needsAction === 0
                  ? `${counts['auto-pass']} auto-passed.`
                  : `${needsAction} need attention · ${counts['auto-pass']} auto-passed.`}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {!processing && needsAction > 0 && (
              <Button size="lg" icon={IconCheck} onClick={onStartReview}>
                Start review ({needsAction})
              </Button>
            )}
            <Button variant="secondary" onClick={onReset}>New batch</Button>
          </div>
        </div>
        <div
          style={{ height: 8, borderRadius: 6, background: 'var(--color-bg-alt)', overflow: 'hidden' }}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={totalFiles}
          aria-valuenow={done}
          aria-label="Batch progress"
        >
          <div style={{
            width: `${(done / Math.max(1, totalFiles)) * 100}%`, height: '100%',
            background: 'var(--color-primary)',
            transition: 'width 240ms ease',
          }} />
        </div>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: 12, marginBottom: 16,
      }}>
        {(['needs-review', 'needs-confirm', 'auto-pass'] as GroupKey[]).map(g => {
          const meta = GROUP_META[g];
          const filterKey: FilterKey = g === 'needs-review' ? 'review' : g === 'needs-confirm' ? 'confirm' : 'pass';
          const active = filter === filterKey;
          return (
            <button
              key={g}
              type="button"
              className="batch-group"
              data-tone={meta.tone}
              data-active={active ? 'true' : undefined}
              onClick={() => setFilter(filterKey)}
            >
              <span className="status__icon"
                style={{ background: `var(--status-${meta.tone}-fg)`, color: '#fff', width: 28, height: 28 }}
                aria-hidden="true">
                <meta.Icon size={14} strokeWidth={3} />
              </span>
              <div style={{ textAlign: 'left', flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 'var(--fs-18)' }}>{counts[g]} {meta.label}</div>
                <div style={{ fontSize: 13, color: 'var(--color-ink-muted)' }}>{meta.desc}</div>
              </div>
            </button>
          );
        })}
      </div>

      <div className="batch-tabs" role="tablist" aria-label="Filter batch results">
        {([
          ['all',     'All',           items.length],
          ['review',  'Needs review',  counts['needs-review']],
          ['confirm', 'Needs confirm', counts['needs-confirm']],
          ['pass',    'Auto-pass',     counts['auto-pass']],
        ] as Array<[FilterKey, string, number]>).map(([k, label, n]) => (
          <button key={k} type="button"
            role="tab"
            aria-selected={filter === k}
            className="batch-tab"
            data-active={filter === k ? 'true' : undefined}
            onClick={() => setFilter(k)}>
            {label} <span className="batch-tab__count">{n}</span>
          </button>
        ))}
      </div>

      {filter === 'all' ? (
        <>
          <GroupSection group="needs-review"  items={items.filter(it => it.group === 'needs-review')}  onOpen={onOpenItem} forceOpen />
          <GroupSection group="needs-confirm" items={items.filter(it => it.group === 'needs-confirm')} onOpen={onOpenItem} forceOpen />
          <GroupSection group="auto-pass"     items={items.filter(it => it.group === 'auto-pass')}     onOpen={onOpenItem} open={autoPassOpen} onToggle={() => setAutoPassOpen(o => !o)} />
        </>
      ) : (
        <ItemList items={filtered} onOpen={onOpenItem} />
      )}

      {!processing && items.length === 0 && (
        <Alert variant="info" title="No items yet">
          <p>Once verifyBatch streams in results they'll appear here.</p>
        </Alert>
      )}
    </>
  );
}

interface GroupSectionProps {
  group: GroupKey;
  items: BatchItemResult[];
  onOpen: (item: BatchItemResult) => void;
  forceOpen?: boolean;
  open?: boolean;
  onToggle?: () => void;
}

function GroupSection({ group, items, onOpen, forceOpen, open, onToggle }: GroupSectionProps) {
  const meta = GROUP_META[group];
  const isOpen = forceOpen || open;
  if (items.length === 0) return null;
  return (
    <section className="batch-section" data-tone={meta.tone}>
      <header className="batch-section__head">
        <span style={{ background: `var(--status-${meta.tone}-fg)`, color: '#fff', width: 28, height: 28, borderRadius: 999, display: 'grid', placeItems: 'center' }} aria-hidden="true">
          <meta.Icon size={14} strokeWidth={3} />
        </span>
        <h3 style={{ margin: 0, flex: 1, fontSize: 'var(--fs-18)' }}>
          {items.length} {meta.label}
        </h3>
        {forceOpen ? (
          <span className="tag">surfaced</span>
        ) : (
          <button type="button" className="btn btn--ghost"
            aria-expanded={!!isOpen}
            onClick={onToggle}>
            {isOpen ? 'Collapse' : `Show ${items.length}`}
            <span aria-hidden="true" style={{
              display: 'inline-block', marginLeft: 4,
              transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)',
              transition: 'transform 160ms',
            }}>
              <IconChevronR size={16} />
            </span>
          </button>
        )}
      </header>
      {isOpen && <ItemList items={items} onOpen={onOpen} />}
    </section>
  );
}

function ItemList({ items, onOpen }: { items: BatchItemResult[]; onOpen: (item: BatchItemResult) => void }) {
  return (
    <ul className="batch-list">
      {items.map(it => <ItemRow key={it.id} item={it} onOpen={onOpen} />)}
    </ul>
  );
}

function ItemRow({ item, onOpen }: { item: BatchItemResult; onOpen: (item: BatchItemResult) => void }) {
  const meta = GROUP_META[item.group];
  const summary = quickSummary(item);
  const brand = (item.result.fields as VerificationField[]).find(f => f.fieldName === 'Brand name');
  const brandText = brand ? brand.extractedValue : '—';
  return (
    <li className="batch-row" style={{ contentVisibility: 'auto', containIntrinsicSize: '0 72px' }}>
      <button
        type="button"
        className="batch-row__btn"
        onClick={() => onOpen(item)}
        aria-label={`Open ${item.fileName}, ${meta.label}`}
      >
        <img src={item.thumbnailUrl} alt="" className="batch-row__thumb" />
        <div className="batch-row__main">
          <div className="batch-row__filename">{item.fileName}</div>
          <div className="batch-row__brand">{brandText}</div>
        </div>
        <div className="batch-row__summary">{summary}</div>
        <StatusBadge status={meta.tone} />
        <span aria-hidden="true" className="batch-row__chevron">
          <IconChevronR size={16} />
        </span>
      </button>
    </li>
  );
}
