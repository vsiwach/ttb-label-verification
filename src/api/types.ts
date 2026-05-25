// src/api/types.ts
// ─────────────────────────────────────────────────────────────────────────────
// THE TTB API CONTRACT — single source of truth for data shapes shared
// between the React client and the FastAPI backend.
// ─────────────────────────────────────────────────────────────────────────────

/** The 3-state status model used everywhere a field verdict appears. */
export type FieldStatus = 'match' | 'likely' | 'flag';

/** One field on a label, compared against the application. */
export interface VerificationField {
  /** Human-readable field name, e.g. "Brand name". */
  fieldName: string;
  /** What the COLA application says. */
  declaredValue: string;
  /** What AI read off the label image. */
  extractedValue: string;
  /** Verdict for this field. */
  status: FieldStatus;
  /** Model confidence, 0..1. */
  confidence: number;
  /** Optional crop of the label region used as evidence (data URL or HTTPS URL). */
  evidenceCropUrl?: string;
  /** Optional regulation citation, e.g. "27 CFR 5.36(b)(1)". */
  regulationCite?: string;
  /** Plain-language reason — used in tooltips / drawers. */
  note?: string;
}

/** Analysis of the mandatory Government Warning panel (27 CFR 16.21/16.22). */
export interface GovernmentWarningAnalysis {
  present: boolean;
  /** Detected text matches the verbatim baseline character-for-character. */
  verbatimMatch: boolean;
  /** "GOVERNMENT WARNING" is all-caps AND bold. */
  casingBoldOk: boolean;
  /** Adequate contrast against background. */
  contrastOk: boolean;
  /** Warning is separate and apart from other label copy. */
  separateAndApart: boolean;
  /** Raw OCR text from the warning region. */
  detectedText: string;
  /** Specific deviations the agent must review. */
  deviations: Array<{ type: string; message: string }>;
  /** Always this constant — included for downstream filtering / display. */
  regulation: '27 CFR 16.21/16.22';
  /** 27 CFR 16.22 minimum type size, computed from the warning bbox + image
   *  DPI when both are available. null when inputs missing (phone photos
   *  without DPI, or extractor returned no bbox) — agent confirms manually. */
  fontSizeOk?: boolean | null;
}

/** Image-quality signal. Drives the "re-upload a sharper image" prompt. */
export interface ImageQuality {
  /** 0..1; lower means the OCR is operating on a worse signal. */
  score: number;
  legible: boolean;
  note?: string;
}

/** Per-request latency breakdown. Attached to every result so the UI can
 *  show how fast the current inference mode is. extractorMs is the bulk
 *  of the time (model call + network); rulesMs is the deterministic
 *  rules engine pass; totalMs is the whole pipeline including image
 *  pre-processing and evidence cropping. */
export interface TimingInfo {
  inferenceMode: string;
  extractorMs: number;
  rulesMs: number;
  totalMs: number;
}

/** The full result of /api/verify. */
export interface VerificationResult {
  fields: VerificationField[];
  governmentWarning: GovernmentWarningAnalysis;
  imageQuality: ImageQuality;
  timing?: TimingInfo;
}

/** What the user (or a saved record) supplies as ground truth from the COLA application. */
export interface ApplicationData {
  brandName: string;
  /** COLA Form 5100.31 Field 16 — Fanciful / Product Name. Labels often
   *  prominently print this (SKU) instead of the registered brewery brand.
   *  Optional; when set, the backend accepts a label-extracted brand match
   *  against either brandName or productName. */
  productName?: string;
  classType: string;
  alcoholContent: string;       // e.g. "45% Alc./Vol. (90 Proof)"
  netContents: string;          // e.g. "750 mL"
  bottlerNameAddress: string;
  countryOfOrigin?: string;     // imports only
  beverageType: 'spirits' | 'wine' | 'beer' | 'malt';
  colaNumber?: string;
}

/** A single item in a batch result. */
export interface BatchItemResult {
  id: string;
  fileName: string;
  thumbnailUrl: string;
  result: VerificationResult;
  /** Derived bucket for the batch dashboard. */
  group: 'auto-pass' | 'needs-confirm' | 'needs-review';
}

/** Callbacks for the streaming verifyLabel() client. */
export interface VerifyLabelOptions {
  /** Override the total simulated stream budget (mock client only). */
  totalMs?: number;
  /** Fires after the government-warning analysis lands. */
  onGovernmentWarning?: (gw: GovernmentWarningAnalysis) => void;
  /** Fires after the image-quality signal lands. */
  onImageQuality?: (iq: ImageQuality) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// THE EXACT REQUIRED VERBATIM GOVERNMENT WARNING TEXT (27 CFR 16.21/16.22).
// Stored as a frozen constant so nothing in the app can accidentally mutate it.
// This is the baseline that GovernmentWarningAnalysis.detectedText is compared against.
// ─────────────────────────────────────────────────────────────────────────────
export const VERBATIM_GOVERNMENT_WARNING: string = Object.freeze(
  'GOVERNMENT WARNING: (1) According to the Surgeon General, women should not '
  + 'drink alcoholic beverages during pregnancy because of the risk of birth defects. '
  + '(2) Consumption of alcoholic beverages impairs your ability to drive a car or '
  + 'operate machinery, and may cause health problems.'
) as string;

/**
 * Derives the dashboard bucket for a verification result.
 *   needs-review  — any flag, missing warning, or non-verbatim warning
 *   needs-confirm — any likely-match field
 *   auto-pass     — everything else
 */
export function groupFor(result: VerificationResult): BatchItemResult['group'] {
  const hasFlag =
    result.fields.some(f => f.status === 'flag')
    || result.governmentWarning.present === false
    || result.governmentWarning.verbatimMatch === false;
  const hasLikely = result.fields.some(f => f.status === 'likely');
  if (hasFlag) return 'needs-review';
  if (hasLikely) return 'needs-confirm';
  return 'auto-pass';
}
