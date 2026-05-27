// src/api/client.ts
// ─────────────────────────────────────────────────────────────────────────────
// THE API CLIENT — typed entry point used by the entire app.
//
// Endpoints:
//   POST /api/verify        body { image, applicationData }      -> VerificationResult
//   POST /api/verify-batch  body { images[], applicationData? }  -> BatchItemResult[]
//
// Backend URL comes from VITE_API_BASE_URL. In dev (npm run dev) the default
// is http://localhost:8000/api. In a deployed build the env var MUST be set
// at build time; if it isn't, requests fail loudly rather than silently
// falling back to fixtures.
// ─────────────────────────────────────────────────────────────────────────────

import type {
  ApplicationData,
  BatchItemResult,
  VerificationField,
  VerificationResult,
  VerifyLabelOptions,
} from './types';

// ── Configuration ───────────────────────────────────────────────────────────
// Vite replaces these literal expressions at transform time with the values
// captured at process-start. If neither is set we fall back to the local
// dev backend on :8000. Production builds MUST set VITE_API_BASE_URL.
const RAW_API_URL: string | undefined = import.meta.env.VITE_API_BASE_URL;
const IS_DEV: boolean = !!import.meta.env.DEV;
const API_BASE_URL: string =
  (RAW_API_URL && RAW_API_URL.trim()) ||
  (IS_DEV ? 'http://localhost:8000/api' : '');

if (!API_BASE_URL) {
  // eslint-disable-next-line no-console
  console.warn(
    '[ttb] VITE_API_BASE_URL not set; verification requests will fail. ' +
    'Set it at build time to point at the backend.',
  );
}

export type OnFieldCallback = (
  field: VerificationField,
  index: number,
  total: number,
) => void;

// ── verifyLabel ─────────────────────────────────────────────────────────────
/**
 * Verify a single label.
 *
 * The backend returns the full VerificationResult as one JSON response.
 * For UI compatibility, this client emits each field via `onField` after
 * the result lands, then fires `onGovernmentWarning` and `onImageQuality`.
 * (True server-side streaming is on the roadmap — N1 in DESIGN.md §10.)
 */
export async function verifyLabel(
  image: Blob | string | null,
  applicationData: ApplicationData,
  onField?: OnFieldCallback,
  opts: VerifyLabelOptions = {},
): Promise<VerificationResult> {
  if (!API_BASE_URL) throw new Error('Backend URL not configured (VITE_API_BASE_URL).');

  const body = new FormData();
  if (image instanceof Blob) body.append('image', image, 'label.jpg');
  else if (typeof image === 'string') body.append('image', image);
  body.append('applicationData', JSON.stringify(applicationData));

  const res = await fetch(`${API_BASE_URL}/verify`, { method: 'POST', body });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`verify failed: ${res.status} ${detail}`);
  }
  const result = (await res.json()) as VerificationResult;

  // Replay fields one-by-one so the UI still gets the streamed-feel effect
  // even though the wire response is a single object. Sub-50ms total.
  if (onField) {
    const fields = result.fields;
    for (let i = 0; i < fields.length; i++) onField(fields[i], i, fields.length);
  }
  if (opts.onGovernmentWarning && result.governmentWarning) {
    opts.onGovernmentWarning(result.governmentWarning);
  }
  if (opts.onImageQuality && result.imageQuality) {
    opts.onImageQuality(result.imageQuality);
  }
  return result;
}

export type OnBatchItemCallback = (
  item: BatchItemResult,
  index: number,
  total: number,
) => void;

// ── verifyBatch ─────────────────────────────────────────────────────────────
/**
 * Verify a batch of labels. The backend fans out concurrent extractor calls
 * (bounded semaphore) and returns the full array once every item resolves.
 */
export async function verifyBatch(
  files: Array<File | Blob | { name?: string }>,
  applicationData?: ApplicationData,
  onItem?: OnBatchItemCallback,
  /** Optional per-file application data (real TTB Form 5100.31 data from
   *  the sample picker). Keyed by File.name. When present, the backend uses
   *  this per item instead of falling back to a single shared or empty
   *  placeholder — preserves real declared values per sample. */
  applicationsByFilename?: Record<string, ApplicationData>,
): Promise<BatchItemResult[]> {
  if (!API_BASE_URL) throw new Error('Backend URL not configured (VITE_API_BASE_URL).');

  const body = new FormData();
  for (const f of files) if (f instanceof Blob) body.append('images', f);
  if (applicationData) body.append('applicationData', JSON.stringify(applicationData));
  if (applicationsByFilename && Object.keys(applicationsByFilename).length > 0) {
    body.append('applicationsByFilename', JSON.stringify(applicationsByFilename));
  }

  const res = await fetch(`${API_BASE_URL}/verify-batch`, { method: 'POST', body });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`verify-batch failed: ${res.status} ${detail}`);
  }
  const items = (await res.json()) as BatchItemResult[];
  if (onItem) {
    for (let i = 0; i < items.length; i++) onItem(items[i], i, items.length);
  }
  return items;
}

export { API_BASE_URL };
