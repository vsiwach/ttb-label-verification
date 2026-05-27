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
import { groupFor } from './types';

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
const BATCH_CONCURRENCY = 3;

const EMPTY_APP_DATA: ApplicationData = {
  brandName: '', classType: '', alcoholContent: '',
  netContents: '', bottlerNameAddress: '', beverageType: 'spirits',
};

/**
 * Verify a batch of labels by fanning out CLIENT-SIDE to /api/verify, one
 * fetch per file with bounded concurrency.
 *
 * Each fetch hits its own Vercel function invocation, so each label has
 * its own 30 s Vercel maxDuration budget instead of the entire batch
 * sharing one. The previous server-side fan-out via /api/verify-batch
 * timed out on Vercel as soon as the batch passed ~4-5 labels because a
 * single Vercel function had to complete the whole gather inside 30 s.
 *
 * The onItem callback now fires AS EACH LABEL FINISHES, not after the
 * whole batch — true streaming UI, the dashboard's "Waiting on the
 * first result…" placeholder is replaced the moment the first label
 * comes back instead of waiting for the slowest.
 *
 * Per-label failures (timeout, 500, etc.) become a synthetic
 * needs-review item with a `verifyError` deviation so one bad label
 * doesn't kill the whole batch.
 */
export async function verifyBatch(
  files: Array<File | Blob | { name?: string }>,
  applicationData?: ApplicationData,
  onItem?: OnBatchItemCallback,
  /** Optional per-file application data (real TTB Form 5100.31 data from
   *  the sample picker). Keyed by File.name. */
  applicationsByFilename?: Record<string, ApplicationData>,
): Promise<BatchItemResult[]> {
  if (!API_BASE_URL) throw new Error('Backend URL not configured (VITE_API_BASE_URL).');

  // Normalize to File[] so we have a reliable .name per item.
  const fileList: File[] = [];
  for (const f of files) {
    if (f instanceof File) fileList.push(f);
    else if (f instanceof Blob) fileList.push(new File([f], (f as { name?: string }).name || 'upload.bin'));
  }

  const total = fileList.length;
  const results: BatchItemResult[] = new Array(total);
  let next = 0;

  async function worker(): Promise<void> {
    while (true) {
      const i = next++;
      if (i >= total) return;
      const file = fileList[i];
      const appData =
        applicationsByFilename?.[file.name]
        ?? applicationData
        ?? EMPTY_APP_DATA;

      try {
        const body = new FormData();
        body.append('image', file);
        body.append('applicationData', JSON.stringify(appData));
        const res = await fetch(`${API_BASE_URL}/verify`, { method: 'POST', body });
        if (!res.ok) {
          const detail = await res.text().catch(() => '');
          throw new Error(`${res.status} ${detail.slice(0, 200)}`);
        }
        const result = (await res.json()) as VerificationResult;
        const item: BatchItemResult = {
          id: file.name,
          fileName: file.name,
          thumbnailUrl: '',
          result,
          group: groupFor(result),
        };
        results[i] = item;
        onItem?.(item, i, total);
      } catch (err) {
        // Per-label failure — surface as a needs-review row rather than
        // aborting the whole batch. The agent sees the error message and
        // can re-upload that single label individually.
        const msg = err instanceof Error ? err.message : String(err);
        const failResult: VerificationResult = {
          fields: [],
          governmentWarning: {
            present: false, verbatimMatch: false, casingBoldOk: false,
            contrastOk: false, separateAndApart: false,
            detectedText: '',
            deviations: [{ type: 'verifyError', message: `Verify failed: ${msg}` }],
            regulation: '27 CFR 16.21/16.22',
          },
          imageQuality: { score: 0, legible: false, note: msg },
        };
        const item: BatchItemResult = {
          id: file.name,
          fileName: file.name,
          thumbnailUrl: '',
          result: failResult,
          group: 'needs-review',
        };
        results[i] = item;
        onItem?.(item, i, total);
      }
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(BATCH_CONCURRENCY, total) }, worker),
  );
  return results;
}

export { API_BASE_URL };
