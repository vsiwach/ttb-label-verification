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
