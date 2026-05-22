# TTB Label Verification — API Contract Reference (locked)

This is the **ground-truth API contract** produced by Claude Design at Prompt 2. It is the seam between the frontend (Claude Design) and the backend (Claude Code). When we build the backend, it must implement these shapes **exactly** so the two halves connect by flipping `USE_MOCK = false` and setting `VITE_API_BASE_URL`.

Captured: from `src/api/types.ts`, `src/api/ttbRules.ts`, `src/api/mockData.ts`, `src/api/client.ts`.

---

## How the backend (Claude Code) must honor this contract

A few specifics, drawn from reading the actual generated code — these are what make the handoff zero-reconciliation:

1. **Return the full JSON, not a stream.** The mock *simulates* streaming via the `onField` / `onGovernmentWarning` / `onImageQuality` callbacks, but the real (`USE_MOCK = false`) path in `client.ts` does a single `POST` and `res.json()`. So the MVP backend should return the **whole `VerificationResult` as one JSON response** from `POST /api/verify`. The streaming *feel* is a frontend affordance. (If we ever want true server-sent streaming, we update both sides together — not needed for the contract as written.)
2. **Endpoints & payloads:**
   - `POST /api/verify` — multipart `FormData`: `image` (the downscaled file) + `applicationData` (JSON string) → returns `VerificationResult`.
   - `POST /api/verify-batch` — multipart `FormData`: repeated `images` + optional `applicationData` (JSON string) → returns `BatchItemResult[]` (a JSON array).
3. **Replicate `groupFor()` server-side.** The batch `group` ('auto-pass' | 'needs-confirm' | 'needs-review') must be computed with the *same* logic the contract defines: `needs-review` if any field is `flag` OR the warning is missing OR not verbatim; `needs-confirm` if any field is `likely`; else `auto-pass`.
4. **Government Warning baseline.** `verbatimMatch` compares `detectedText` against the `VERBATIM_GOVERNMENT_WARNING` constant (reproduced below — it matches 27 CFR 16.21 exactly). Keep that constant identical on the backend.
5. **Beverage types.** The enum is `'spirits' | 'wine' | 'beer' | 'malt'`. The backend should treat **both `'beer'` and `'malt'` as Part 7 malt-beverage rules** (alcohol content optional unless added nonbeverage flavors).
6. **Citations are illustrative — upgrade them.** The mock `regulationCite` values use **pre-2020 section numbers** (e.g., `27 CFR 5.32`, `5.35`, `5.37`). The 2020 modernization renumbered Parts 4/5/7; the backend rules engine should cite the **current** sections (mandatory info: spirits §5.63, wine §4.32, malt §7.63; warning §16.21/§16.22). The *shape* `regulationCite?: string` stays the same — only the values get corrected.
7. **`thumbnailUrl` and `evidenceCropUrl`** are strings (data URL or HTTPS). The backend's image pipeline should generate real crops/thumbnails; until then a placeholder URL satisfies the type.

---

## `src/api/types.ts`

```ts
// src/api/types.ts
// ─────────────────────────────────────────────────────────────────────────────
// THE TTB API CONTRACT — single source of truth for data shapes.
// The future real backend MUST implement these shapes exactly. The mock
// client in src/api/client.ts returns them today; swapping in a real
// fetch() call later is a one-line change (flip USE_MOCK to false).
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
  /** Warning text meets the minimum type size for the container. */
  fontSizeOk: boolean;
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
}

/** Image-quality signal. Drives the "re-upload a sharper image" prompt. */
export interface ImageQuality {
  /** 0..1; lower means the OCR is operating on a worse signal. */
  score: number;
  legible: boolean;
  note?: string;
}

/** The full result of /api/verify. */
export interface VerificationResult {
  fields: VerificationField[];
  governmentWarning: GovernmentWarningAnalysis;
  imageQuality: ImageQuality;
}

/** What the user (or a saved record) supplies as ground truth from the COLA application. */
export interface ApplicationData {
  brandName: string;
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
```

## `src/api/ttbRules.ts`

```ts
// src/api/ttbRules.ts
// ─────────────────────────────────────────────────────────────────────────────
// TTB mandatory-field rules per beverage type.
//
// COMMON to all alcohol beverages (per 27 CFR Parts 4, 5, 7):
//   - Brand name
//   - Class / type designation
//   - Net contents
//   - Name & address of the bottler / producer / importer
//   - Country of origin (imports only — see ApplicationData.countryOfOrigin)
//   - Government Warning (27 CFR 16.21/16.22) — required on ALL beverages
//     ≥ 0.5% ABV, regardless of beverage type. Surfaced separately because
//     it is not a field on ApplicationData.
//
// SPIRITS & WINE: alcohol content statement IS required on the label.
// BEER / MALT: ABV is OPTIONAL by federal rule UNLESS the product contains
//              added nonbeverage flavoring materials (then ABV is required).
//              State laws may also require/prohibit ABV — beyond TTB scope.
// ─────────────────────────────────────────────────────────────────────────────

import type { ApplicationData } from './types';

export type BeverageType = ApplicationData['beverageType'];

export interface RequiredFieldsOptions {
  /** Imported products require a country-of-origin statement. */
  imported?: boolean;
  /** Beer / malt products with added flavors require an ABV statement. */
  containsAddedFlavors?: boolean;
}

/** The required ApplicationData keys for a given beverage type. */
export type ApplicationDataKey = keyof ApplicationData;

const COMMON: readonly ApplicationDataKey[] = Object.freeze([
  'brandName',
  'classType',
  'netContents',
  'bottlerNameAddress',
]);

/**
 * Returns the list of required ApplicationData fields for a given beverage type.
 * The Government Warning is always additionally required at the result level
 * (see governmentWarningRequired) — it is NOT a field on ApplicationData.
 */
export function requiredFields(
  beverageType: BeverageType,
  opts: RequiredFieldsOptions = {},
): ApplicationDataKey[] {
  const { imported = false, containsAddedFlavors = false } = opts;
  const base: ApplicationDataKey[] = [...COMMON];

  if (beverageType === 'spirits' || beverageType === 'wine') {
    base.push('alcoholContent');
  }
  if ((beverageType === 'beer' || beverageType === 'malt') && containsAddedFlavors) {
    base.push('alcoholContent');
  }
  if (imported) {
    base.push('countryOfOrigin');
  }
  return base;
}

/**
 * The Government Warning is required on every alcohol beverage label ≥ 0.5% ABV.
 * Caller may override at the application level for non-alcoholic products.
 */
export function governmentWarningRequired(_beverageType: BeverageType): boolean {
  return true;
}
```

## `src/api/mockData.ts`

```ts
// src/api/mockData.ts
// ─────────────────────────────────────────────────────────────────────────────
// Realistic TTB mock fixtures: three scenarios + saved application records.
//
// Scenario A — OLD TOM DISTILLERY (all matches; the demo "happy path")
// Scenario B — STONE'S THROW   (brand casing near-match + net contents flag)
// Scenario C — NORTHWIND BREWING (title-case + paraphrased + small Govt Warning)
//
// evidenceCropUrl and thumbnails use tiny inline SVG data URLs so this file
// is self-contained — no external image dependencies for the demo.
// ─────────────────────────────────────────────────────────────────────────────

import {
  VERBATIM_GOVERNMENT_WARNING,
  type ApplicationData,
  type VerificationResult,
} from './types';

// ── Tiny SVG generator for evidence crops & thumbnails ───────────────────────
interface SvgPlaceholderOpts {
  w?: number;
  h?: number;
  label?: string;
  bg?: string;
  fg?: string;
}

export function svgPlaceholder({
  w = 120,
  h = 80,
  label = '',
  bg = '#eef1f7',
  fg = '#1a4480',
}: SvgPlaceholderOpts = {}): string {
  const safe = String(label).replace(/[<>&]/g, '');
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}">`
    + `<rect width="${w}" height="${h}" fill="${bg}"/>`
    + `<rect x="0" y="0" width="${w}" height="${h}" fill="url(#h)" opacity=".4"/>`
    + `<defs><pattern id="h" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">`
    + `<rect width="5" height="10" fill="${fg}" opacity=".08"/></pattern></defs>`
    + `<text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle"`
    + ` font-family="ui-monospace,SF Mono,Consolas,monospace" font-size="11" fill="${fg}">${safe}</text>`
    + `</svg>`;
  return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}

// ── Saved application records (the user can "load" instead of typing) ───────
export const SAVED_APPLICATIONS: ApplicationData[] = [
  {
    colaNumber: '25-001234',
    brandName: 'OLD TOM DISTILLERY',
    classType: 'Kentucky Straight Bourbon Whiskey',
    alcoholContent: '45% Alc./Vol. (90 Proof)',
    netContents: '750 mL',
    bottlerNameAddress: 'Old Tom Distillery, Frankfort, Kentucky',
    beverageType: 'spirits',
  },
  {
    colaNumber: '25-002301',
    brandName: "STONE'S THROW",
    classType: 'California Red Table Wine',
    alcoholContent: '13.5% Alc./Vol.',
    netContents: '750 mL',
    bottlerNameAddress: "Stone's Throw Cellars, Sonoma, California",
    beverageType: 'wine',
  },
  {
    colaNumber: '25-003988',
    brandName: 'NORTHWIND BREWING',
    classType: 'India Pale Ale',
    alcoholContent: '6.8% Alc./Vol.',
    netContents: '12 FL OZ',
    bottlerNameAddress: 'Northwind Brewing Co., Bend, Oregon',
    beverageType: 'beer',
  },
];

// ── A named scenario pairs an application record with its expected result ───
export interface MockScenario {
  label: string;
  applicationData: ApplicationData;
  result: VerificationResult;
}

// ── Scenario A — all matches (demo happy path) ──────────────────────────────
const SCENARIO_A: MockScenario = {
  label: 'OLD TOM DISTILLERY — all matches',
  applicationData: SAVED_APPLICATIONS[0],
  result: {
    fields: [
      { fieldName: 'Brand name',          declaredValue: 'OLD TOM DISTILLERY',
        extractedValue: 'OLD TOM DISTILLERY', status: 'match', confidence: 0.99,
        regulationCite: '27 CFR 5.32(a)',
        evidenceCropUrl: svgPlaceholder({ label: 'brand crop', bg: '#f6efe1', fg: '#7a5300' }) },
      { fieldName: 'Class & type',        declaredValue: 'Kentucky Straight Bourbon Whiskey',
        extractedValue: 'Kentucky Straight Bourbon Whiskey', status: 'match', confidence: 0.97,
        regulationCite: '27 CFR 5.35',
        evidenceCropUrl: svgPlaceholder({ label: 'class crop', bg: '#f0e9d8', fg: '#5a3b00' }) },
      { fieldName: 'Alcohol content',     declaredValue: '45% Alc./Vol. (90 Proof)',
        extractedValue: '45% Alc./Vol. (90 Proof)', status: 'match', confidence: 0.96,
        regulationCite: '27 CFR 5.37',
        evidenceCropUrl: svgPlaceholder({ label: 'ABV crop' }) },
      { fieldName: 'Net contents',        declaredValue: '750 mL',
        extractedValue: '750 mL', status: 'match', confidence: 0.99,
        regulationCite: '27 CFR 5.38',
        evidenceCropUrl: svgPlaceholder({ label: 'net qty crop' }) },
      { fieldName: 'Bottler name/address', declaredValue: 'Old Tom Distillery, Frankfort, Kentucky',
        extractedValue: 'Old Tom Distillery, Frankfort, KY', status: 'match', confidence: 0.95,
        regulationCite: '27 CFR 5.36',
        evidenceCropUrl: svgPlaceholder({ label: 'bottler crop' }) },
    ],
    governmentWarning: {
      present: true,
      verbatimMatch: true,
      casingBoldOk: true,
      fontSizeOk: true,
      contrastOk: true,
      separateAndApart: true,
      detectedText: VERBATIM_GOVERNMENT_WARNING,
      deviations: [],
      regulation: '27 CFR 16.21/16.22',
    },
    imageQuality: { score: 0.92, legible: true, note: 'Sharp; even lighting.' },
  },
};

// ── Scenario B — STONE'S THROW casing near-match + net contents flag ────────
const SCENARIO_B: MockScenario = {
  label: "STONE'S THROW — casing near-match + net contents flag",
  applicationData: SAVED_APPLICATIONS[1],
  result: {
    fields: [
      { fieldName: 'Brand name',          declaredValue: "STONE'S THROW",
        extractedValue: "Stone's Throw", status: 'likely', confidence: 0.88,
        regulationCite: '27 CFR 4.33',
        note: 'Casing differs from the application. Visual brand otherwise matches.',
        evidenceCropUrl: svgPlaceholder({ label: 'brand crop', bg: '#fff5dc', fg: '#7a4a00' }) },
      { fieldName: 'Class & type',        declaredValue: 'California Red Table Wine',
        extractedValue: 'California Red Table Wine', status: 'match', confidence: 0.96,
        regulationCite: '27 CFR 4.34',
        evidenceCropUrl: svgPlaceholder({ label: 'class crop' }) },
      { fieldName: 'Alcohol content',     declaredValue: '13.5% Alc./Vol.',
        extractedValue: '13.5% Alc./Vol.', status: 'match', confidence: 0.95,
        regulationCite: '27 CFR 4.36',
        evidenceCropUrl: svgPlaceholder({ label: 'ABV crop' }) },
      { fieldName: 'Net contents',        declaredValue: '750 mL',
        extractedValue: '700 mL', status: 'flag', confidence: 0.97,
        regulationCite: '27 CFR 4.37',
        note: 'Net contents on the label does not match the application. Possible mislabel.',
        evidenceCropUrl: svgPlaceholder({ label: 'net qty', bg: '#f7dfd5', fg: '#8a1a00' }) },
      { fieldName: 'Bottler name/address', declaredValue: "Stone's Throw Cellars, Sonoma, California",
        extractedValue: "Stone's Throw Cellars, Sonoma, CA", status: 'match', confidence: 0.94,
        regulationCite: '27 CFR 4.35',
        evidenceCropUrl: svgPlaceholder({ label: 'bottler crop' }) },
    ],
    governmentWarning: {
      present: true,
      verbatimMatch: true,
      casingBoldOk: true,
      fontSizeOk: true,
      contrastOk: true,
      separateAndApart: true,
      detectedText: VERBATIM_GOVERNMENT_WARNING,
      deviations: [],
      regulation: '27 CFR 16.21/16.22',
    },
    imageQuality: { score: 0.86, legible: true },
  },
};

// ── Scenario C — title-case + paraphrased + small Government Warning ────────
const SCENARIO_C_WARNING_TEXT =
  'Government Warning: (1) According to the Surgeon General, women should not '
  + 'drink alcoholic beverages during pregnancy because of the risk of birth defects. '
  + '(2) Drinking alcoholic beverages impairs your ability to drive a car or operate '
  + 'machinery and may cause health problems.';

const SCENARIO_C: MockScenario = {
  label: 'Government Warning violation (Title Case + paraphrased + small type)',
  applicationData: SAVED_APPLICATIONS[2],
  result: {
    fields: [
      { fieldName: 'Brand name',          declaredValue: 'NORTHWIND BREWING',
        extractedValue: 'NORTHWIND BREWING', status: 'match', confidence: 0.98,
        regulationCite: '27 CFR 7.22',
        evidenceCropUrl: svgPlaceholder({ label: 'brand crop' }) },
      { fieldName: 'Class & type',        declaredValue: 'India Pale Ale',
        extractedValue: 'India Pale Ale', status: 'match', confidence: 0.95,
        regulationCite: '27 CFR 7.24',
        evidenceCropUrl: svgPlaceholder({ label: 'class crop' }) },
      { fieldName: 'Net contents',        declaredValue: '12 FL OZ',
        extractedValue: '12 FL. OZ.', status: 'likely', confidence: 0.91,
        regulationCite: '27 CFR 7.27',
        note: 'Punctuation differs ("FL. OZ." vs "FL OZ"). Equivalent.',
        evidenceCropUrl: svgPlaceholder({ label: 'net qty crop' }) },
      { fieldName: 'Bottler name/address', declaredValue: 'Northwind Brewing Co., Bend, Oregon',
        extractedValue: 'Northwind Brewing Co., Bend, OR', status: 'match', confidence: 0.93,
        regulationCite: '27 CFR 7.25',
        evidenceCropUrl: svgPlaceholder({ label: 'bottler crop' }) },
    ],
    governmentWarning: {
      present: true,
      verbatimMatch: false,
      casingBoldOk: false,
      fontSizeOk: false,
      contrastOk: true,
      separateAndApart: true,
      detectedText: SCENARIO_C_WARNING_TEXT,
      deviations: [
        { type: 'casing',   message: '"GOVERNMENT WARNING" must be all capitals and bold; detected title case.' },
        { type: 'wording',  message: 'Statement wording does not match the required verbatim text.' },
        { type: 'fontSize', message: 'Warning text appears below the minimum type size for this container.' },
      ],
      regulation: '27 CFR 16.21/16.22',
    },
    imageQuality: { score: 0.79, legible: true, note: 'Warning band area is lower-resolution than the rest of the label.' },
  },
};

export const SCENARIOS: Record<'A' | 'B' | 'C', MockScenario> = {
  A: SCENARIO_A,
  B: SCENARIO_B,
  C: SCENARIO_C,
};

/** Build a tall thumbnail (3:4) for a scenario. Used by the batch dashboard. */
export function thumbFor(scenarioKey: 'A' | 'B' | 'C'): string {
  const s = SCENARIOS[scenarioKey];
  return svgPlaceholder({
    w: 120,
    h: 160,
    label: s.applicationData.brandName.split(' ')[0],
  });
}
```

## `src/api/client.ts`

```ts
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
const USE_MOCK = true;

/** When wired to the real backend, override via VITE_API_BASE_URL at build time. */
const API_BASE_URL: string =
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ((import.meta as any)?.env?.VITE_API_BASE_URL as string | undefined) ?? '/api';

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
```

---

## Dependency summary

The four files are self-contained at runtime — they only import from each other:

- `types.ts` — no imports (standalone)
- `ttbRules.ts` — imports a type from `./types`
- `mockData.ts` — imports from `./types`
- `client.ts` — imports from `./types` and `./mockData`

No external npm packages (no axios/zod/date-fns). Needs only a Vite + React + TS scaffold and `import.meta.env.VITE_API_BASE_URL` (so `src/vite-env.d.ts` should have `/// <reference types="vite/client" />`). UI primitives (`StatusBadge`, `Button`, `Card`, `FileDropzone`, `FieldRow`, skeletons, `Alert`) consume `FieldStatus`, `VerificationField`, and `VerificationResult` from `types.ts`.
