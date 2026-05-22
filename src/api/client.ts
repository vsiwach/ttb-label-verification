// src/api/client.ts
// ─────────────────────────────────────────────────────────────────────────────
// THE API CLIENT — typed entry point used by the entire app.
//
// Endpoints (future real backend will implement exactly these):
//   POST /api/verify        body { image, applicationData }      -> VerificationResult
//   POST /api/verify-batch  body { images[], applicationData? }  -> BatchItemResult[]
//                           (real backend may return { jobId } + polling)
//
// For now USE_MOCK = true returns fixtures from ./mockData.ts and SIMULATES
// streaming by emitting fields one-by-one over ~2–4 seconds total via the
// onField callback. Swap USE_MOCK to false and point API_BASE_URL at the
// real service when the backend exists.
// ─────────────────────────────────────────────────────────────────────────────

import type {
  ApplicationData,
  BatchItemResult,
  VerificationField,
  VerificationResult,
  VerifyLabelOptions,
} from './types';
import { groupFor } from './types';
import { SCENARIOS, thumbFor, type MockScenario } from './mockData';

// ── Configuration ───────────────────────────────────────────────────────────
/**
 * When VITE_API_BASE_URL is unset (or empty), the client runs against the
 * fixtures in ./mockData.ts. The moment you deploy with VITE_API_BASE_URL
 * pointing at the real backend, USE_MOCK flips to false — no code change.
 */
const API_BASE_URL: string =
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ((import.meta as any)?.env?.VITE_API_BASE_URL as string | undefined)?.trim() || '';

const USE_MOCK = API_BASE_URL.length === 0;

// ── helpers ─────────────────────────────────────────────────────────────────
const wait = (ms: number): Promise<void> => new Promise(r => setTimeout(r, ms));
const rand = (lo: number, hi: number): number => lo + Math.random() * (hi - lo);

function pickScenario(applicationData: ApplicationData | null | undefined): MockScenario {
  if (!applicationData) return SCENARIOS.A;
  const brand = (applicationData.brandName || '').toUpperCase();
  if (brand.includes('STONE'))     return SCENARIOS.B;
  if (brand.includes('NORTHWIND')) return SCENARIOS.C;
  return SCENARIOS.A;
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
 * Streams fields one-by-one via `onField` over ~2–4 s total (simulated),
 * then resolves with the final VerificationResult so callers can also
 * `await` the whole thing if they don't care about streaming.
 *
 * @param image            Downscaled JPEG (Blob/File/dataURL) — ignored by the mock.
 * @param applicationData  The COLA application data to compare against.
 * @param onField          Optional per-field streaming callback.
 * @param opts             totalMs override + onGovernmentWarning / onImageQuality.
 */
export async function verifyLabel(
  image: Blob | string | null,
  applicationData: ApplicationData,
  onField?: OnFieldCallback,
  opts: VerifyLabelOptions = {},
): Promise<VerificationResult> {
  if (!USE_MOCK) {
    // Real implementation:
    const body = new FormData();
    if (image instanceof Blob) body.append('image', image);
    else if (typeof image === 'string') body.append('image', image);
    body.append('applicationData', JSON.stringify(applicationData));
    const res = await fetch(`${API_BASE_URL}/verify`, { method: 'POST', body });
    if (!res.ok) throw new Error(`verify failed: ${res.status}`);
    return res.json() as Promise<VerificationResult>;
  }

  const scenario = pickScenario(applicationData);
  const totalMs = opts.totalMs ?? rand(2000, 4000);
  const fields = scenario.result.fields;
  // Distribute ~70% of the budget across field streams, save 30% for the
  // government warning + image quality at the end.
  const fieldBudget = totalMs * 0.7;
  const perFieldBase = fieldBudget / fields.length;

  for (let i = 0; i < fields.length; i++) {
    // Jitter per-field delay so streaming feels organic rather than ticked.
    await wait(perFieldBase * rand(0.5, 1.4));
    if (onField) onField(fields[i], i, fields.length);
  }

  // Trailing budget: governmentWarning + imageQuality.
  await wait(totalMs * 0.15);
  if (opts.onGovernmentWarning) opts.onGovernmentWarning(scenario.result.governmentWarning);
  await wait(totalMs * 0.10);
  if (opts.onImageQuality)      opts.onImageQuality(scenario.result.imageQuality);

  return scenario.result;
}

export type OnBatchItemCallback = (
  item: BatchItemResult,
  index: number,
  total: number,
) => void;

// ── verifyBatch ─────────────────────────────────────────────────────────────
/**
 * Verify a batch of labels.
 *
 * Fans out: each item finishes on its own jittered timeline and is emitted
 * via `onItem` as soon as it completes — so the batch dashboard can update
 * progressively without waiting on the slowest item. Resolves with the
 * full ordered array once everything is done.
 */
export async function verifyBatch(
  files: Array<File | Blob | { name?: string }>,
  applicationData?: ApplicationData,
  onItem?: OnBatchItemCallback,
): Promise<BatchItemResult[]> {
  if (!USE_MOCK) {
    const body = new FormData();
    for (const f of files) if (f instanceof Blob) body.append('images', f);
    if (applicationData) body.append('applicationData', JSON.stringify(applicationData));
    const res = await fetch(`${API_BASE_URL}/verify-batch`, { method: 'POST', body });
    if (!res.ok) throw new Error(`verify-batch failed: ${res.status}`);
    return res.json() as Promise<BatchItemResult[]>;
  }

  const scenarioKeys: Array<'A' | 'B' | 'C'> = ['A', 'B', 'C'];
  const results: BatchItemResult[] = new Array(files.length);

  // Kick all items off in parallel; their completion is staggered by jitter.
  const promises = files.map(async (file, idx) => {
    // Rotate through scenarios so the demo shows a mix of outcomes.
    const key = scenarioKeys[idx % scenarioKeys.length];
    const scenario = SCENARIOS[key];
    await wait(rand(800, 3200));

    const itemResult: BatchItemResult = {
      id: `b-${Date.now()}-${idx}`,
      fileName: (file as File)?.name ?? `label-${idx + 1}.jpg`,
      thumbnailUrl: thumbFor(key),
      result: scenario.result,
      group: groupFor(scenario.result),
    };
    results[idx] = itemResult;
    if (onItem) onItem(itemResult, idx, files.length);
  });

  await Promise.all(promises);
  return results;
}

// ── Re-exports for the rest of the app ──────────────────────────────────────
export { USE_MOCK, API_BASE_URL };
