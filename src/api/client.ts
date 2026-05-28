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
  GovernmentWarningAnalysis,
  ImageQuality,
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
 * When any callback is provided (onField / opts.onGovernmentWarning /
 * opts.onImageQuality) this calls the streaming endpoint
 * (/api/verify/stream) and fires callbacks as NDJSON events arrive —
 * image_quality at ~200 ms, Qwen-owned fields at ~3 s, Haiku-owned
 * fields at ~3.5 s, warning + done at ~5 s. The promise resolves with
 * the assembled VerificationResult after the 'done' event.
 *
 * When no callbacks are provided this falls back to the single-JSON
 * /api/verify endpoint — the path used by verifyBatch() below where
 * each fan-out call wants one atomic result, not a stream.
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

  const wantsStreaming = !!(onField || opts.onGovernmentWarning || opts.onImageQuality);
  if (!wantsStreaming) {
    const res = await fetch(`${API_BASE_URL}/verify`, { method: 'POST', body });
    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      throw new Error(`verify failed: ${res.status} ${detail}`);
    }
    return (await res.json()) as VerificationResult;
  }

  const res = await fetch(`${API_BASE_URL}/verify/stream`, { method: 'POST', body });
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => '');
    throw new Error(`verify failed: ${res.status} ${detail}`);
  }

  // Assemble the final result from streamed events.
  const fields: VerificationField[] = [];
  let governmentWarning: GovernmentWarningAnalysis | undefined;
  let imageQuality: ImageQuality | undefined;
  let timing: VerificationResult['timing'];

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let totalFieldsHint = 0;

  const handleEvent = (event: string, data: Record<string, unknown>): void => {
    switch (event) {
      case 'image_quality': {
        imageQuality = data as unknown as ImageQuality;
        opts.onImageQuality?.(imageQuality);
        break;
      }
      case 'field': {
        const f = data as unknown as VerificationField;
        fields.push(f);
        totalFieldsHint = Math.max(totalFieldsHint, fields.length);
        onField?.(f, fields.length - 1, totalFieldsHint);
        break;
      }
      case 'warning': {
        governmentWarning = data as unknown as GovernmentWarningAnalysis;
        opts.onGovernmentWarning?.(governmentWarning);
        break;
      }
      case 'done': {
        if (data.imageQuality && !imageQuality) imageQuality = data.imageQuality as ImageQuality;
        if (data.timing) timing = data.timing as VerificationResult['timing'];
        break;
      }
      case 'error': {
        throw new Error(`verify failed: ${String((data as { detail?: string }).detail || 'unknown')}`);
      }
    }
  };

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl = buffer.indexOf('\n');
    while (nl !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) {
        const msg = JSON.parse(line) as { event: string; data: Record<string, unknown> };
        handleEvent(msg.event, msg.data);
      }
      nl = buffer.indexOf('\n');
    }
  }
  // Flush any trailing line that did not end with '\n'.
  const tail = buffer.trim();
  if (tail) {
    const msg = JSON.parse(tail) as { event: string; data: Record<string, unknown> };
    handleEvent(msg.event, msg.data);
  }

  // Fallback shapes so callers never see an undefined sub-tree (mirrors
  // the non-streaming response's required-field contract).
  const result: VerificationResult = {
    fields,
    governmentWarning: governmentWarning ?? {
      present: false,
      verbatimMatch: false,
      casingBoldOk: false,
      contrastOk: false,
      separateAndApart: false,
      detectedText: '',
      deviations: [],
      regulation: '27 CFR 16.21/16.22',
    },
    imageQuality: imageQuality ?? { score: 1, legible: true },
    timing,
  };
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
