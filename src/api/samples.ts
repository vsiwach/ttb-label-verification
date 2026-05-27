// Client for the backend /api/samples endpoints.
// Fetches the list of pre-loaded COLA samples (synthetic + real) and
// downloads their label images on demand.

import type { ApplicationData } from './types';
import { API_BASE_URL } from './client';

export type SampleKind = 'synthetic' | 'real' | 'ttb-live';

export interface SampleSummary {
  id: string;
  kind: SampleKind;
  imageUrl: string;          // relative path: /api/samples/{id}/image
  applicationData: ApplicationData;
  expectedOutcome: 'auto-pass' | 'needs-confirm' | 'needs-review';
  note: string;
}

/** Fetch the curated picker subset (auto-pass + a few fails). */
export async function fetchSamples(): Promise<SampleSummary[]> {
  if (!API_BASE_URL) throw new Error('Backend URL not configured.');
  const res = await fetch(`${API_BASE_URL}/samples`);
  if (!res.ok) throw new Error(`fetch samples failed: ${res.status}`);
  return res.json() as Promise<SampleSummary[]>;
}

/** Fetch every sample (COLA Cloud + TTB-live + synthetic) for the gallery. */
export async function fetchAllSamples(): Promise<SampleSummary[]> {
  if (!API_BASE_URL) throw new Error('Backend URL not configured.');
  const res = await fetch(`${API_BASE_URL}/samples/all`);
  if (!res.ok) throw new Error(`fetch all samples failed: ${res.status}`);
  return res.json() as Promise<SampleSummary[]>;
}

/** Fetch a sample's label image as a Blob. */
export async function fetchSampleImage(sample: SampleSummary): Promise<Blob> {
  if (!API_BASE_URL) throw new Error('Backend URL not configured.');
  // imageUrl from backend is "/api/samples/{id}/image" — prepend the
  // API_BASE_URL host (strip the duplicate "/api" prefix).
  const base = API_BASE_URL.replace(/\/api$/, '');
  const res = await fetch(`${base}${sample.imageUrl}`);
  if (!res.ok) throw new Error(`fetch sample image failed: ${res.status}`);
  return res.blob();
}
