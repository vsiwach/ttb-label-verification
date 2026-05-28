import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import type { ApplicationData, BatchItemResult, VerificationField } from '../api/types';
import { verifyBatch } from '../api/client';
import { fetchAllSamples, fetchSampleImage, type SampleSummary } from '../api/samples';
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
import { preWarmModal } from '../utils/preWarm';

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

/** Empty ApplicationData for batch items that were dropped (not picked from
 *  samples) — the engine still extracts every field, declared-side is just
 *  blank so the UI shows "not declared on application" rather than
 *  comparing against synthetic placeholder data. */
function emptyAppData(): ApplicationData {
  return {
    colaNumber: '',
    brandName: '',
    classType: '',
    alcoholContent: '',
    netContents: '',
    bottlerNameAddress: '',
    beverageType: 'spirits',
  };
}

/** Convert a Blob to a data: URL so the result page can render it without
 *  needing a network round-trip (the original sample images come from the
 *  /api/samples endpoint; user-uploaded files don't have an endpoint to fetch). */
function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
export default function BatchPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [phase, setPhase]   = useState<'upload' | 'processing' | 'done'>('upload');
  const [files, setFiles]   = useState<QueuedFile[]>([]);
  const [items, setItems]   = useState<BatchItemResult[]>([]);
  const [shared, setShared] = useState<ApplicationData | null>(null);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [error, setError]   = useState<string | null>(null);
  // Auto-pass items still need agent confirmation — open by default so the
  // agent sees every item and isn't tempted to skip a bucket.
  const [autoPassOpen, setAutoPassOpen] = useState(true);

  // Per-file maps for samples added via the picker:
  //   - appDataByFile: the REAL TTB application data (replaces the old
  //     guessAppDataFor synthetic placeholder logic)
  //   - imageDataUrlByFile: the actual label image so /result can render it
  //     instead of a broken image
  // Refs (not state) because the picker writes them imperatively and we don't
  // want re-renders on every map update — the consumers read on click.
  const appDataByFile      = useRef<Map<string, ApplicationData>>(new Map());
  const imageDataUrlByFile = useRef<Map<string, string>>(new Map());

  // Kick the Modal container awake on mount so it's warm by the time
  // the agent finishes queueing files and clicks Process.
  useEffect(() => { preWarmModal(); }, []);

  function handleFiles(list: File[], opts?: { appData?: Record<string, ApplicationData>; dataUrls?: Record<string, string> }) {
    // De-dupe by name+size so the picker doesn't enqueue the same sample twice
    // if the user clicks "Add" repeatedly. Files from the dropzone are unique
    // by construction (filesystem path); from the picker we keyed on sample id.
    setFiles(prev => {
      const seen = new Set(prev.map(f => `${(f as File).name}:${(f as File).size}`));
      const next = [...prev];
      for (const f of list) {
        const key = `${f.name}:${f.size}`;
        if (!seen.has(key)) { seen.add(key); next.push(f); }
      }
      return next;
    });
    if (opts?.appData) {
      for (const [k, v] of Object.entries(opts.appData)) appDataByFile.current.set(k, v);
    }
    if (opts?.dataUrls) {
      for (const [k, v] of Object.entries(opts.dataUrls)) imageDataUrlByFile.current.set(k, v);
    }
  }
  function clearFiles() {
    setFiles([]); setItems([]); setPhase('upload'); setError(null);
    appDataByFile.current.clear();
    imageDataUrlByFile.current.clear();
  }

  // Deep-link from /samples?for=batch: ?samples=id1,id2,id3 — fetch each
  // sample, wrap as a File with its TTB application data + image data URL,
  // and queue them all in one shot. Strips the query param after handling
  // so a refresh doesn't re-queue.
  const queuedSamplesRef = useRef<string | null>(null);
  useEffect(() => {
    const raw = searchParams.get('samples');
    if (!raw || queuedSamplesRef.current === raw) return;
    queuedSamplesRef.current = raw;
    const ids = raw.split(',').map(s => s.trim()).filter(Boolean);
    if (ids.length === 0) return;

    (async () => {
      try {
        const all = await fetchAllSamples();
        const picks = ids
          .map(id => all.find(s => s.id === id))
          .filter((s): s is SampleSummary => !!s);
        const appData: Record<string, ApplicationData>  = {};
        const dataUrls: Record<string, string>          = {};
        const files = await Promise.all(picks.map(async s => {
          const blob = await fetchSampleImage(s);
          const ext  = blob.type.includes('jpeg') ? 'jpg' : (blob.type.includes('webp') ? 'webp' : 'png');
          const name = `${s.id}.${ext}`;
          appData[name]  = s.applicationData;
          dataUrls[name] = await blobToDataUrl(blob);
          return new File([blob], name, { type: blob.type || 'image/jpeg' });
        }));
        handleFiles(files, { appData, dataUrls });
      } catch (e: any) {
        setError(`Couldn't queue samples: ${e?.message || e}`);
      } finally {
        setSearchParams({}, { replace: true });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  async function startProcessing() {
    if (files.length === 0) return;
    setPhase('processing');
    setItems([]);
    setError(null);
    // Snapshot the picker's per-file application data into a plain object
    // so the backend uses real TTB form data per item (not synthetic).
    const perFile: Record<string, ApplicationData> = {};
    appDataByFile.current.forEach((v, k) => { perFile[k] = v; });
    try {
      await verifyBatch(
        files,
        shared ?? undefined,
        (item) => { setItems(prev => [...prev, item]); },
        Object.keys(perFile).length > 0 ? perFile : undefined,
      );
      setPhase('done');
    } catch (e: any) {
      setError(String(e?.message || e || 'unknown error'));
      // Stay in processing phase so the Alert is visible alongside the
      // "0 done" header. User can hit "New batch" to reset.
    }
  }

  function openItem(item: BatchItemResult) {
    verifyStore.reset();
    // Use the picker-supplied image data URL if available; otherwise fall
    // back to the (often empty) thumbnailUrl the backend returned. No
    // synthetic placeholders.
    const dataUrl = imageDataUrlByFile.current.get(item.fileName) || item.thumbnailUrl || '';
    const image: UploadedImage = {
      blob: null,
      dataUrl,
      fileName: item.fileName,
      width: 0, height: 0,
      originalWidth: 0, originalHeight: 0,
      originalSize: 0, optimizedSize: 0,
    };
    // Per-item REAL application data from the picker. If the user dropped
    // their own file (no picker entry), use empty ApplicationData — the
    // engine will then surface "not declared on application" notes per
    // field, which is honest, instead of comparing the label to some
    // synthetic placeholder.
    const perItemAppData =
      shared
      ?? appDataByFile.current.get(item.fileName)
      ?? emptyAppData();
    // The batch already produced a full VerificationResult for this item;
    // hand it straight to /result so it renders immediately without firing
    // a second verify call. The previous version reset everything and
    // let /result re-verify, which failed with 422 because the batch's
    // UploadedImage carries blob=null (it never owned the Blob, only a
    // data URL for thumbnail rendering).
    verifyStore.setState({
      image,
      applicationData: perItemAppData,
      status: 'done',
      result: {
        fields: item.result.fields,
        governmentWarning: item.result.governmentWarning,
        imageQuality: item.result.imageQuality,
        timing: item.result.timing ?? null,
      },
      error: null,
    });
    // Hand a fromBatch hint to /result so it can render a visible
    // "Back to batch" link — the only other way back is the browser
    // back button which isn't discoverable.
    navigate('/result', { state: { fromBatch: true } });
  }

  function startReview() {
    const queue = items.filter(it => it.group !== 'auto-pass');
    // Snapshot the per-file maps into plain objects so the review session
    // survives across route navigations (refs reset with the page).
    const appDataByFileSnapshot: Record<string, ApplicationData> = {};
    const imageDataUrlByFileSnapshot: Record<string, string> = {};
    appDataByFile.current.forEach((v, k) => { appDataByFileSnapshot[k] = v; });
    imageDataUrlByFile.current.forEach((v, k) => { imageDataUrlByFileSnapshot[k] = v; });
    verifyStore.setState({
      reviewSession: {
        queue, shared, startedAt: Date.now(),
        appDataByFile: appDataByFileSnapshot,
        imageDataUrlByFile: imageDataUrlByFileSnapshot,
      },
    });
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
        <>
          {error && (
            <div style={{ marginBottom: 16 }}>
              <Alert variant="error" title="Batch processing failed">
                {error}
              </Alert>
            </div>
          )}
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
        </>
      )}
    </div>
  );
}

interface UploadPanelProps {
  files: QueuedFile[];
  shared: ApplicationData | null;
  setShared: (a: ApplicationData | null) => void;
  onFiles: (files: File[], opts?: { appData?: Record<string, ApplicationData>; dataUrls?: Record<string, string> }) => void;
  onClear: () => void;
  onStart: () => void;
}

function UploadPanel({ files, shared, setShared, onFiles, onClear, onStart }: UploadPanelProps) {
  const navigate = useNavigate();
  const totalBytes = files.reduce((a, f) => a + ((f as File).size || 0), 0);
  const ready = files.length > 0;

  return (
    <>
      <FileDropzone
        accept="image/jpeg,image/png"
        multiple
        onFiles={onFiles}
        label="Drop a folder of label images here"
        hint="JPEG or PNG, hundreds of files are fine."
        buttonLabel="Browse sample labels"
        icon={IconFolder}
        onBrowse={() => navigate('/samples?for=batch')}
        pickerFallbackLabel="Or pick files from your computer"
      />

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
                {processing
                  ? `Modal Qwen + Anthropic Haiku + Tesseract in parallel — typically ~5 s per label end-to-end. Results stream in below as each label finishes.`
                  : needsAction === 0
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

      {/* Buckets + filter tabs only appear once at least one item has
          come back. While the batch is still running with nothing done,
          showing "0 Needs review / 0 Needs confirm / 0 Auto-pass" is
          visual noise — the progress bar already tells the agent
          something is happening. */}
      {items.length > 0 && (
        <>
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
        </>
      )}

      {/* While processing with 0 items done, show a calm placeholder card
          instead of empty bucket tiles. Once the first item streams in,
          the buckets + tabs above appear and this block disappears. */}
      {processing && items.length === 0 && (
        <div className="card" style={{
          padding: 32, marginBottom: 16, textAlign: 'center',
          background: 'var(--color-primary-tint-2)',
          border: '1px dashed var(--color-primary-tint)',
        }}>
          <p style={{ margin: 0, fontSize: 'var(--fs-16)', fontWeight: 600, color: 'var(--color-ink)' }}>
            Waiting on the first result…
          </p>
          <p style={{ margin: '6px 0 0', fontSize: 'var(--fs-14)', color: 'var(--color-ink-muted)' }}>
            Buckets and per-label rows appear here as each verify finishes.
          </p>
        </div>
      )}

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

