import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { ApplicationData } from '../api/types';
import type { BeverageType } from '../api/ttbRules';
import { requiredFields } from '../api/ttbRules';
import { fetchAllSamples, fetchSampleImage, fetchSamples, type SampleSummary } from '../api/samples';
import Alert from '../components/Alert';
import Button from '../components/Button';
import FileDropzone from '../components/FileDropzone';
import { SkeletonBlock, SkeletonLine } from '../components/Skeleton';
import { IconArrowR, IconCheck, IconInfo, IconWarn } from '../components/icons';
import { downscaleImage, formatBytes, type DownscaleResult } from '../utils/downscaleImage';
import { preWarmModal } from '../utils/preWarm';
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [app, setApp]             = useState<ApplicationData>(EMPTY_APP);
  const [imported, setImported]   = useState(false);
  const [image, setImage]         = useState<WithImagePreview | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [touched, setTouched]     = useState<Record<string, boolean>>({});
  const [submitAttempted, setSubmitAttempted] = useState(false);

  // Fetch the curated picker subset on mount + kick the Modal container
  // awake so it's warm by the time the agent clicks Verify.
  const [samples, setSamples]     = useState<SampleSummary[]>([]);
  const [samplesError, setSamplesError] = useState<string | null>(null);
  const [loadingSampleId, setLoadingSampleId] = useState<string | null>(null);
  useEffect(() => {
    preWarmModal();
    fetchSamples()
      .then(setSamples)
      .catch(err => setSamplesError(err instanceof Error ? err.message : String(err)));
  }, []);

  // Deep-link from /samples gallery: ?sample=<id>. We resolve against the
  // full sample universe (not just the picker) so any card in the gallery
  // can pre-fill the form, even ones the picker doesn't surface.
  const preloadedRef = useRef<string | null>(null);
  useEffect(() => {
    const id = searchParams.get('sample');
    if (!id || preloadedRef.current === id) return;
    preloadedRef.current = id;
    // Try the curated picker list first (cheap, already loaded). Fall
    // back to fetching the full set so gallery deep-links always work.
    const hit = samples.find(s => s.id === id);
    const resolve: Promise<SampleSummary | undefined> = hit
      ? Promise.resolve(hit)
      : fetchAllSamples().then(list => list.find(s => s.id === id));
    resolve.then(s => {
      if (s) loadSample(s);
      // Clear the query param so a refresh doesn't re-trigger the load.
      setSearchParams({}, { replace: true });
    }).catch(err => setSamplesError(err instanceof Error ? err.message : String(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, samples]);

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
        Browse the saved COLA samples to load a paired application + label, or
        drop your own. We'll compare every required field, audit the
        Government Warning, and flag anything that needs your attention.
      </p>

      {samplesError && (
        <div style={{ marginBottom: 16 }}>
          <Alert variant="error" title="Couldn't load samples">{samplesError}</Alert>
        </div>
      )}

      <div className="two-col">
        <section aria-labelledby="sec-upload">
          <h2 id="sec-upload" style={{ color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: 12, fontWeight: 700 }}>Label image</h2>
          {loadingSampleId && (
            <p style={{ margin: '0 0 12px', fontSize: 13, color: 'var(--color-ink-muted)' }}>
              Loading sample {loadingSampleId}…
            </p>
          )}
          {!image && !optimizing && (
            <FileDropzone
              accept="image/jpeg,image/png"
              onFiles={handleFiles}
              label="Drop a label image here"
              hint="JPEG or PNG, up to 20 MB."
              buttonLabel="Browse sample labels"
              onBrowse={() => navigate('/samples')}
              pickerFallbackLabel="Or pick a file from your computer"
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
  const [zoomed, setZoomed] = useState(false);
  return (
    <div className="card" style={{ padding: 16 }}>
      <button
        type="button"
        onClick={() => setZoomed(true)}
        aria-label="Open larger view of the label image"
        style={{
          // Big readable preview — the agent uses this to read ABV /
          // Net contents / Government Warning text off TTB-live labels
          // where those fields aren't carried on the form.
          display: 'block', width: '100%',
          padding: 0, border: '1px solid var(--color-line)', borderRadius: 4,
          background: '#f5f5f5', cursor: 'zoom-in', overflow: 'hidden',
        }}
      >
        <img
          src={image.dataUrl}
          alt={`Preview of ${image.fileName} — click to enlarge`}
          style={{
            display: 'block', width: '100%', maxHeight: 520,
            // contain (not cover) so warning text and ABV aren't cropped out.
            objectFit: 'contain', background: '#f5f5f5',
          }}
        />
      </button>
      {zoomed && (
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
      <div style={{ marginTop: 12 }}>
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
  );
}

