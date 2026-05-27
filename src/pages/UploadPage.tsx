import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { ApplicationData } from '../api/types';
import type { BeverageType } from '../api/ttbRules';
import { requiredFields } from '../api/ttbRules';
import { fetchSampleImage, fetchSamples, type SampleSummary } from '../api/samples';
import Alert from '../components/Alert';
import Button from '../components/Button';
import FileDropzone from '../components/FileDropzone';
import { SkeletonBlock, SkeletonLine } from '../components/Skeleton';
import { IconArrowR, IconCheck, IconInfo, IconLightning, IconWarn } from '../components/icons';
import { downscaleImage, formatBytes, type DownscaleResult } from '../utils/downscaleImage';
import { verifyStore, type UploadedImage } from '../store/verifyStore';

type ApplicationKey = keyof ApplicationData;

const FIELD_LABEL: Record<string, string> = {
  brandName:          'Brand name',
  classType:          'Class / type',
  alcoholContent:     'Alcohol content',
  netContents:        'Net contents',
  bottlerNameAddress: 'Name & address of bottler, producer, or importer',
  countryOfOrigin:    'Country of origin',
};

const FIELD_HINT: Record<string, string> = {
  brandName:          'Exactly as it appears on the COLA application (e.g. OLD TOM DISTILLERY).',
  classType:          'e.g. Kentucky Straight Bourbon Whiskey · India Pale Ale · California Red Table Wine.',
  alcoholContent:     'e.g. 45% Alc./Vol. (90 Proof) or 13.5% Alc./Vol.',
  netContents:        'e.g. 750 mL, 12 FL OZ, 1.75 L.',
  bottlerNameAddress: 'Full legal name and city/state on the label.',
  countryOfOrigin:    'Required for imported product only.',
};

const EMPTY_APP: ApplicationData = {
  brandName: '',
  classType: '',
  alcoholContent: '',
  netContents: '',
  bottlerNameAddress: '',
  countryOfOrigin: '',
  beverageType: 'spirits',
  colaNumber: '',
};

type WithImagePreview = DownscaleResult & { fileName: string };

export default function UploadPage() {
  const navigate = useNavigate();
  const [app, setApp]             = useState<ApplicationData>(EMPTY_APP);
  const [imported, setImported]   = useState(false);
  const [image, setImage]         = useState<WithImagePreview | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [touched, setTouched]     = useState<Record<string, boolean>>({});
  const [submitAttempted, setSubmitAttempted] = useState(false);

  // Fetch the curated list of sample COLAs (9 synthetic + 10 real) on mount.
  const [samples, setSamples]     = useState<SampleSummary[]>([]);
  const [samplesError, setSamplesError] = useState<string | null>(null);
  const [loadingSampleId, setLoadingSampleId] = useState<string | null>(null);
  useEffect(() => {
    fetchSamples()
      .then(setSamples)
      .catch(err => setSamplesError(err instanceof Error ? err.message : String(err)));
  }, []);

  const required = useMemo<ApplicationKey[]>(
    () => requiredFields(app.beverageType, { imported, containsAddedFlavors: false }) as ApplicationKey[],
    [app.beverageType, imported],
  );
  const isRequired = (key: ApplicationKey) => required.includes(key);

  // The form's submit gate. Bottler is required ON THE LABEL (the engine
  // checks the label for it), but real COLA filings often don't carry the
  // bottler line in the application record — the engine handles the
  // empty-declared case gracefully ("Application did not declare this
  // field; label content shown for review"). So we don't block submit
  // on a missing bottler; brand + class (and ABV for spirits/wine, COO
  // for imports) are enough for the verification to be useful.
  const BOTTLER_KEY: ApplicationKey = 'bottlerNameAddress';
  const submitRequired = useMemo<ApplicationKey[]>(
    () => required.filter(k => k !== BOTTLER_KEY),
    [required],
  );

  const fieldErrors = useMemo(() => {
    const errs: Record<string, string> = {};
    for (const key of submitRequired) {
      const v = app[key];
      if (typeof v !== 'string' || !v.trim()) {
        errs[key] = `${FIELD_LABEL[key]} is required for ${app.beverageType}.`;
      }
    }
    return errs;
  }, [app, submitRequired]);

  const formValid = Object.keys(fieldErrors).length === 0;
  const ready     = !!image && formValid;

  const blockedReason = useMemo(() => {
    if (!image) return 'Add a label image to continue.';
    const missing = submitRequired.filter(k => {
      const v = app[k];
      return typeof v !== 'string' || !v.trim();
    });
    if (missing.length === 0) return null;
    if (missing.length === 1) return `Add the ${FIELD_LABEL[missing[0] as string].toLowerCase()}.`;
    return `Fill in ${missing.length} more required fields.`;
  }, [image, app, submitRequired]);

  async function handleFiles(files: File[]) {
    if (!files.length) return;
    const f = files[0];
    setImageError(null);
    setOptimizing(true);
    try {
      const result = await downscaleImage(f, { maxMegapixels: 2, quality: 0.85 });
      setImage({ ...result, fileName: f.name });
    } catch (err) {
      setImageError(err instanceof Error ? err.message : String(err));
      setImage(null);
    } finally {
      setOptimizing(false);
    }
  }

  async function loadSample(sample: SampleSummary) {
    setApp({ ...EMPTY_APP, ...sample.applicationData });
    setImported(!!sample.applicationData.countryOfOrigin);
    setTouched({});
    setImageError(null);
    setLoadingSampleId(sample.id);
    setOptimizing(true);
    try {
      const blob = await fetchSampleImage(sample);
      // The image endpoint serves WebP for real samples and PNG for synthetic;
      // give the downscaler a sensible filename.
      const ext = (blob.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
      const file = new File([blob], `${sample.id}.${ext}`, { type: blob.type });
      const result = await downscaleImage(file, { maxMegapixels: 2, quality: 0.85 });
      setImage({ ...result, fileName: file.name });
    } catch (err) {
      setImageError(err instanceof Error ? err.message : String(err));
      setImage(null);
    } finally {
      setOptimizing(false);
      setLoadingSampleId(null);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitAttempted(true);
    if (!ready || !image) return;
    const uploaded: UploadedImage = {
      blob: image.blob,
      dataUrl: image.dataUrl,
      width: image.width,
      height: image.height,
      originalSize: image.originalSize,
      optimizedSize: image.optimizedSize,
      originalWidth: image.originalWidth,
      originalHeight: image.originalHeight,
      fileName: image.fileName,
    };
    verifyStore.setState({
      image: uploaded,
      applicationData: {
        ...app,
        countryOfOrigin: imported ? app.countryOfOrigin : undefined,
      },
      status: 'idle',
      result: { fields: [], governmentWarning: null, imageQuality: null, timing: null },
      error: null,
    });
    navigate('/result');
  }

  return (
    <form className="container" onSubmit={handleSubmit} noValidate>
      <h1>Verify a label</h1>
      <p style={{ fontSize: 'var(--fs-18)', color: 'var(--color-ink-muted)', marginBottom: 24, maxWidth: 'none' }}>
        Pick a saved COLA below to load a paired application + label, or paste
        in your own. We'll compare every required field, audit the Government
        Warning, and flag anything that needs your attention.
      </p>

      <SamplePicker
        samples={samples}
        error={samplesError}
        loadingId={loadingSampleId}
        onPick={loadSample}
      />

      <div className="two-col">
        <section aria-labelledby="sec-upload">
          <h2 id="sec-upload" style={{ color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: 12, fontWeight: 700 }}>Label image</h2>
          {!image && !optimizing && (
            <FileDropzone
              accept="image/jpeg,image/png"
              onFiles={handleFiles}
              label="Or drop your own label image"
              hint="JPEG or PNG, up to 20 MB."
              buttonLabel="Choose a file…"
            />
          )}

          {optimizing && (
            <div className="dropzone" aria-busy="true" aria-live="polite">
              <SkeletonBlock height={64} style={{ width: 64, borderRadius: 32 }} />
              <p style={{ fontSize: 'var(--fs-18)', fontWeight: 600, margin: 0 }}>Optimizing your image…</p>
              <SkeletonLine width="60%" />
              <SkeletonLine width="40%" />
              <span className="sr-only">Optimizing image. Please wait.</span>
            </div>
          )}

          {imageError && !optimizing && (
            <div style={{ marginTop: 12 }}>
              <Alert variant="error" title="That image couldn't be read" onDismiss={() => setImageError(null)}>
                <p>{imageError}</p>
              </Alert>
            </div>
          )}

          {image && !optimizing && (
            <ImagePreview image={image} onReplace={() => { setImage(null); setImageError(null); }} />
          )}
        </section>

        <section aria-labelledby="sec-app">
          <h2 id="sec-app" style={{ color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: 12, fontWeight: 700 }}>Application data</h2>

          <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="field__label" style={{ padding: 0 }}>
              Beverage type <span style={{ color: 'var(--color-ink-muted)', fontWeight: 500 }}>(required)</span>
            </legend>
            <span className="field__hint">Determines which fields are mandatory under TTB rules.</span>
            <div role="radiogroup" aria-label="Beverage type"
              style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))', gap: 8, marginTop: 8 }}>
              {(['spirits', 'wine', 'beer', 'malt'] as BeverageType[]).map(bt => {
                const checked = app.beverageType === bt;
                return (
                  <label key={bt} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    padding: '10px 12px', borderRadius: 4, cursor: 'pointer',
                    border: '1px solid ' + (checked ? 'var(--color-primary)' : 'var(--color-line-strong)'),
                    background: checked ? 'var(--color-primary-tint-2)' : '#fff',
                    color: checked ? 'var(--color-primary)' : 'var(--color-ink)',
                    fontWeight: checked ? 700 : 500,
                    textTransform: 'capitalize',
                    boxShadow: checked ? 'inset 0 0 0 1px var(--color-primary)' : 'none',
                    minHeight: 44,
                  }}>
                    <input
                      type="radio"
                      name="beverageType"
                      value={bt}
                      checked={checked}
                      onChange={() => setApp(a => ({ ...a, beverageType: bt }))}
                      className="sr-only"
                    />
                    {bt}
                  </label>
                );
              })}
            </div>
            <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--color-ink-subtle)' }}>
              Required for <strong style={{ textTransform: 'capitalize' }}>{app.beverageType}</strong>:{' '}
              {required.map(k => FIELD_LABEL[k as string]).join(' · ')} · Government Warning.
            </p>
          </fieldset>

          {(['brandName', 'classType', 'alcoholContent', 'netContents', 'bottlerNameAddress'] as ApplicationKey[]).map(k => (
            <FormInput
              key={k}
              keyName={k}
              placeholder={placeholderFor(k)}
              required={required}
              app={app}
              setApp={setApp}
              touched={touched}
              setTouched={setTouched}
              submitAttempted={submitAttempted}
              fieldErrors={fieldErrors}
            />
          ))}

          <div className="field" style={{ marginBottom: imported ? 24 : 8 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={imported}
                onChange={(e) => setImported(e.target.checked)}
                style={{ width: 20, height: 20 }}
              />
              <span style={{ fontWeight: 600 }}>This is an imported product</span>
            </label>
            <span className="field__hint" style={{ paddingLeft: 32 }}>
              Imports must show a country-of-origin statement on the label.
            </span>
          </div>
          {imported && (
            <FormInput
              keyName="countryOfOrigin"
              placeholder="e.g. Product of Scotland"
              required={required}
              app={app}
              setApp={setApp}
              touched={touched}
              setTouched={setTouched}
              submitAttempted={submitAttempted}
              fieldErrors={fieldErrors}
            />
          )}
        </section>
      </div>

      <hr className="divider" style={{ marginTop: 40 }} />

      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
        padding: '8px 0 40px',
      }}>
        <Button
          type="submit"
          size="lg"
          trailingIcon={IconArrowR}
          disabled={!ready}
          aria-describedby={!ready ? 'submit-hint' : undefined}
          style={{ minWidth: 280, maxWidth: '100%', fontSize: 'var(--fs-20)' }}
        >
          Verify label
        </Button>
        {!ready && (
          <p id="submit-hint" style={{
            margin: 0, color: 'var(--color-ink-muted)', fontSize: 'var(--fs-16)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <IconInfo size={16} aria-hidden="true" />
            {blockedReason}
          </p>
        )}
        {ready && (
          <p style={{
            margin: 0, color: 'var(--status-match-fg)', fontSize: 'var(--fs-16)',
            display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600,
          }}>
            <IconCheck size={16} aria-hidden="true" />
            Ready to verify. Results stream in over ~3 seconds.
          </p>
        )}
      </div>
    </form>
  );
}

function placeholderFor(k: ApplicationKey): string {
  switch (k) {
    case 'brandName':          return 'e.g. OLD TOM DISTILLERY';
    case 'classType':          return 'e.g. Kentucky Straight Bourbon Whiskey';
    case 'alcoholContent':     return 'e.g. 45% Alc./Vol. (90 Proof)';
    case 'netContents':        return 'e.g. 750 mL';
    case 'bottlerNameAddress': return 'e.g. Old Tom Distillery, Frankfort, Kentucky';
    case 'countryOfOrigin':    return 'e.g. Product of Scotland';
    default: return '';
  }
}

interface FormInputProps {
  keyName: ApplicationKey;
  placeholder: string;
  required: ApplicationKey[];
  app: ApplicationData;
  setApp: React.Dispatch<React.SetStateAction<ApplicationData>>;
  touched: Record<string, boolean>;
  setTouched: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  submitAttempted: boolean;
  fieldErrors: Record<string, string>;
}

function FormInput({ keyName, placeholder, required, app, setApp, touched, setTouched, submitAttempted, fieldErrors }: FormInputProps) {
  const id = `f-${keyName}`;
  const errId = `${id}-err`;
  const hintId = `${id}-hint`;
  const err = (touched[keyName as string] || submitAttempted) ? fieldErrors[keyName as string] : undefined;
  const isReq = required.includes(keyName);
  return (
    <div className={`field${err ? ' field--error' : ''}`}>
      <label className="field__label" htmlFor={id}>
        {FIELD_LABEL[keyName as string]}{' '}
        {isReq && <span style={{ color: 'var(--color-ink-muted)', fontWeight: 500 }}>(required)</span>}
      </label>
      <span className="field__hint" id={hintId}>{FIELD_HINT[keyName as string]}</span>
      <input
        id={id}
        className="field__input"
        type="text"
        placeholder={placeholder}
        value={(app[keyName] as string) || ''}
        aria-required={isReq || undefined}
        aria-invalid={!!err || undefined}
        aria-describedby={`${hintId}${err ? ' ' + errId : ''}`}
        onBlur={() => setTouched(t => ({ ...t, [keyName as string]: true }))}
        onChange={(e) => setApp(a => ({ ...a, [keyName]: e.target.value }))}
      />
      {err && (
        <span id={errId} className="field__error" role="alert">
          <IconWarn size={14} aria-hidden="true" /> {err}
        </span>
      )}
    </div>
  );
}

function ImagePreview({ image, onReplace }: { image: WithImagePreview; onReplace: () => void }) {
  const saved = image.originalSize > 0 ? Math.round((1 - image.optimizedSize / image.originalSize) * 100) : 0;
  const shrunk = image.optimizedSize < image.originalSize;
  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <img
          src={image.dataUrl}
          alt={`Preview of ${image.fileName}`}
          style={{
            width: 120, height: 160, objectFit: 'cover', borderRadius: 4,
            border: '1px solid var(--color-line)', flexShrink: 0, background: '#f5f5f5',
          }}
        />
        <div style={{ flex: '1 1 200px', minWidth: 0 }}>
          <p style={{
            margin: 0, fontWeight: 700, fontSize: 'var(--fs-16)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>{image.fileName}</p>
          <p style={{ margin: '4px 0 12px', color: 'var(--color-ink-muted)', fontSize: 14 }}>
            {image.originalWidth}×{image.originalHeight} → {image.width}×{image.height} px
          </p>
          <div style={{
            background: shrunk ? 'var(--status-match-bg)' : 'var(--status-info-bg)',
            border: '1px solid ' + (shrunk ? 'var(--status-match-border)' : 'var(--status-info-border)'),
            borderRadius: 4, padding: '8px 12px',
            fontSize: 14, color: shrunk ? 'var(--status-match-fg)' : 'var(--status-info-fg)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <IconCheck size={16} aria-hidden="true" />
            {shrunk ? (
              <span><strong>Optimized for fast upload</strong> — was {formatBytes(image.originalSize)}, now {formatBytes(image.optimizedSize)} ({saved}% smaller).</span>
            ) : (
              <span><strong>Already small</strong> — {formatBytes(image.optimizedSize)}. Skipped recompression.</span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={onReplace}
              style={{ minHeight: 36, padding: '0 12px', fontSize: 14 }}
            >
              Replace image
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface SamplePickerProps {
  samples: SampleSummary[];
  error: string | null;
  loadingId: string | null;
  onPick: (s: SampleSummary) => void | Promise<void>;
}

const VERDICT_TINT: Record<string, { bg: string; fg: string; label: string }> = {
  'auto-pass':     { bg: 'var(--status-match-bg)',  fg: 'var(--status-match-fg)',  label: 'auto-pass' },
  'needs-confirm': { bg: 'var(--status-likely-bg)', fg: 'var(--status-likely-fg)', label: 'needs-confirm' },
  'needs-review':  { bg: 'var(--status-flag-bg)',   fg: 'var(--status-flag-fg)',   label: 'needs-review' },
};

function SamplePicker({ samples, error, loadingId, onPick }: SamplePickerProps) {
  const [query, setQuery]   = useState('');
  const [bucket, setBucket] = useState<'all' | 'auto-pass' | 'needs-confirm' | 'needs-review'>('all');
  const [showAll, setShowAll] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return samples.filter(s => {
      if (bucket !== 'all' && s.expectedOutcome !== bucket) return false;
      if (!q) return true;
      const hay = [
        s.applicationData.brandName,
        s.applicationData.classType,
        s.applicationData.beverageType,
        s.applicationData.countryOfOrigin || '',
        s.applicationData.colaNumber || '',
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [samples, query, bucket]);

  const visible = showAll ? filtered : filtered.slice(0, 18);

  return (
    <div className="card" style={{
      padding: 16, marginBottom: 24, background: 'var(--color-primary-tint-2)',
      border: '1px solid var(--color-primary-tint)',
    }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 8 }}>
        <IconLightning size={18} style={{ color: 'var(--color-primary)' }} />
        <strong style={{ fontSize: 'var(--fs-16)' }}>Load a sample COLA</strong>
        <span style={{ fontSize: 12, color: 'var(--color-ink-subtle)', marginLeft: 'auto' }}>
          {samples.length} real labels available
        </span>
      </div>
      <p style={{ margin: '0 0 8px', fontSize: 'var(--fs-14)', color: 'var(--color-ink-muted)' }}>
        Real TTB-approved labels from the public COLA registry. Pick one to load both
        the artwork and its paired Form 5100.31 application data. In production this list
        comes from the TTB filing system directly.
      </p>
      <p style={{ margin: '0 0 12px', fontSize: 12, color: 'var(--color-ink-subtle)' }}>
        The verdict pill is a typical-output hint — Claude is non-deterministic,
        so the actual run may land one bucket up or down. HITL is the safety net.
      </p>

      {error && (
        <Alert variant="error" title="Couldn't load samples">{error}</Alert>
      )}

      {!error && samples.length === 0 && (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--color-ink-subtle)' }}>Loading…</p>
      )}

      {samples.length > 0 && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="search"
            placeholder="Search brand, class, country…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            style={{
              flex: '1 1 220px', minWidth: 0,
              padding: '8px 12px', fontSize: 14,
              border: '1px solid var(--color-line-strong)', borderRadius: 4,
              background: '#fff',
            }}
          />
          <div role="tablist" style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
            {([
              { k: 'all',           label: 'All' },
              { k: 'auto-pass',     label: 'Auto-pass' },
              { k: 'needs-confirm', label: 'Confirm' },
              { k: 'needs-review',  label: 'Review' },
            ] as const).map(opt => (
              <button
                key={opt.k}
                type="button"
                onClick={() => setBucket(opt.k)}
                style={{
                  padding: '6px 10px', fontSize: 12, fontWeight: 600,
                  border: '1px solid ' + (bucket === opt.k ? 'var(--color-primary)' : 'var(--color-line-strong)'),
                  background: bucket === opt.k ? 'var(--color-primary)' : '#fff',
                  color: bucket === opt.k ? '#fff' : 'var(--color-ink)',
                  borderRadius: 4, cursor: 'pointer',
                }}
              >{opt.label}</button>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {visible.map(s => {
          const tint = VERDICT_TINT[s.expectedOutcome] || VERDICT_TINT['auto-pass'];
          const isLoading = loadingId === s.id;
          return (
            <button
              key={s.id}
              type="button"
              className="btn btn--secondary"
              style={{
                minHeight: 36, padding: '6px 12px', fontSize: 13,
                display: 'inline-flex', alignItems: 'center', gap: 8,
                opacity: isLoading ? 0.6 : 1,
              }}
              disabled={loadingId !== null}
              title={s.note}
              onClick={() => onPick(s)}
            >
              <span style={{ fontWeight: 600 }}>{s.applicationData.brandName}</span>
              <span style={{
                fontSize: 11, padding: '2px 6px', borderRadius: 999,
                background: tint.bg, color: tint.fg, fontWeight: 600,
                textTransform: 'lowercase',
              }}>{tint.label}</span>
              {isLoading && <span style={{ fontSize: 11, color: 'var(--color-ink-subtle)' }}>loading…</span>}
            </button>
          );
        })}
      </div>

      {filtered.length > visible.length && (
        <p style={{ margin: '12px 0 0', fontSize: 13 }}>
          Showing {visible.length} of {filtered.length}.{' '}
          <button
            type="button"
            onClick={() => setShowAll(true)}
            style={{
              background: 'none', border: 'none', color: 'var(--color-primary)',
              fontWeight: 600, cursor: 'pointer', padding: 0,
            }}
          >Show all {filtered.length}</button>
        </p>
      )}
      {showAll && filtered.length > 18 && (
        <p style={{ margin: '12px 0 0', fontSize: 13 }}>
          <button
            type="button"
            onClick={() => setShowAll(false)}
            style={{
              background: 'none', border: 'none', color: 'var(--color-primary)',
              fontWeight: 600, cursor: 'pointer', padding: 0,
            }}
          >Collapse</button>
        </p>
      )}
    </div>
  );
}
