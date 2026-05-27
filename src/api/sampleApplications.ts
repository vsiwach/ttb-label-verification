// Previously held synthetic SAMPLE_APPLICATIONS (OLD TOM DISTILLERY,
// STONE'S THROW, etc.) used as placeholder "declared" data for batch
// items. That was wrong — the batch page now uses each sample's REAL
// TTB application data, captured by the picker, with empty fallback
// for user-dropped files. The export is kept as an empty array so any
// legacy import doesn't hard-fail.
//
// If you need to restore this for tests, see git history before commit
// `aa53194` (May 2026).
import type { ApplicationData } from './types';

export const SAMPLE_APPLICATIONS: ApplicationData[] = [];
