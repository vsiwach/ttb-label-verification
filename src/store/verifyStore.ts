// Tiny shared store for cross-route verification state. No state library —
// useSyncExternalStore over a plain object.
import { useSyncExternalStore } from 'react';
import type {
  ApplicationData,
  BatchItemResult,
  GovernmentWarningAnalysis,
  ImageQuality,
  TimingInfo,
  VerificationField,
} from '../api/types';

export interface UploadedImage {
  blob: Blob | null;
  dataUrl: string;
  width: number;
  height: number;
  originalWidth: number;
  originalHeight: number;
  originalSize: number;
  optimizedSize: number;
  fileName: string;
}

export interface ReviewSession {
  queue: BatchItemResult[];
  shared: ApplicationData | null;
  startedAt: number;
}

export interface StreamingResult {
  fields: VerificationField[];
  governmentWarning: GovernmentWarningAnalysis | null;
  imageQuality: ImageQuality | null;
  timing: TimingInfo | null;
}

export interface VerifyStoreState {
  image: UploadedImage | null;
  applicationData: ApplicationData | null;
  status: 'idle' | 'streaming' | 'done' | 'error';
  result: StreamingResult;
  error: Error | null;
  reviewSession: ReviewSession | null;
}

const initial: VerifyStoreState = {
  image: null,
  applicationData: null,
  status: 'idle',
  result: { fields: [], governmentWarning: null, imageQuality: null, timing: null },
  error: null,
  reviewSession: null,
};

let state: VerifyStoreState = initial;
const listeners = new Set<() => void>();

function getState(): VerifyStoreState { return state; }

export type StatePatch =
  | Partial<VerifyStoreState>
  | ((prev: VerifyStoreState) => VerifyStoreState);

export function setState(patch: StatePatch): void {
  state = typeof patch === 'function' ? patch(state) : { ...state, ...patch };
  listeners.forEach(l => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function reset(): void {
  setState({
    image: null,
    applicationData: null,
    status: 'idle',
    result: { fields: [], governmentWarning: null, imageQuality: null, timing: null },
    error: null,
    // Note: reviewSession intentionally NOT cleared so users can navigate
    // /review → /result → back without losing the queue.
  });
}

export function useVerifyStore(): VerifyStoreState {
  return useSyncExternalStore(subscribe, getState, getState);
}

export const verifyStore = { getState, setState, subscribe, reset };
