// Client for the backend /api/samples endpoints.
// Fetches the list of pre-loaded COLA samples (synthetic + real) and
// downloads their label images on demand.

import type { ApplicationData } from './types';
import { API_BASE_URL } from './client';

export type SampleKind = 'synthetic' | 'real';

export interface SampleSummary {
  id: string;
  kind: SampleKind;
  imageUrl: string;          // relative path: /api/samples/{id}/image
  applicationData: ApplicationData;
  expectedOutcome: 'auto-pass' | 'needs-confirm' | 'needs-review';
  note: string;
}

/** Fetch the list of available samples from the backend. */
export async function fetchSamples(): Promise<SampleSummary[]> {
  if (!API_BASE_URL) throw new Error('Backend URL not configured.');
  const res = await fetch(`${API_BASE_URL}/samples`);
  if (!res.ok) throw new Error(`fetch samples failed: ${res.status}`);
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
