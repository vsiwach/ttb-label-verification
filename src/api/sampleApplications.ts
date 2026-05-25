// Saved COLA application records used to pre-fill the form in /upload and
// /batch. These pair with the 9 synthetic label images in test/synthetic/
// so an agent can run the full TTB workflow end-to-end without typing.
//
// Source of truth: test/synthetic/expected_results.json. These are NOT
// mock results — only the form-side application fields. The actual
// verdict comes from the backend rules engine reading the real label image.

import type { ApplicationData } from './types';

export const SAMPLE_APPLICATIONS: ApplicationData[] = [
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
  {
    colaNumber: '25-004102',
    brandName: 'CEDAR & SAGE',
    classType: 'Distilled Gin',
    alcoholContent: '40% Alc./Vol. (80 Proof)',
    netContents: '750 mL',
    bottlerNameAddress: 'Cedar & Sage Spirits, Portland, Oregon',
    beverageType: 'spirits',
  },
  {
    colaNumber: '25-005517',
    brandName: 'VALLEY CREST',
    classType: 'Sonoma County Chardonnay',
    alcoholContent: '13.5% Alc./Vol.',
    netContents: '750 mL',
    bottlerNameAddress: 'Valley Crest Winery, Sonoma, California',
    beverageType: 'wine',
  },
  {
    colaNumber: '25-006023',
    brandName: 'IRON ANCHOR',
    classType: 'Premium Lager Beer',
    alcoholContent: '',
    netContents: '12 FL OZ',
    bottlerNameAddress: 'Iron Anchor Brewing Co., Milwaukee, Wisconsin',
    beverageType: 'beer',
  },
  {
    colaNumber: '25-007840',
    brandName: 'BRIGHT WAVE',
    classType: 'Black Cherry Hard Seltzer',
    alcoholContent: '5% Alc./Vol.',
    netContents: '12 FL OZ',
    bottlerNameAddress: 'Bright Wave Beverage Co., Austin, Texas',
    beverageType: 'malt',
  },
  {
    colaNumber: '25-008311',
    brandName: 'GLEN ARDEN',
    classType: 'Blended Scotch Whisky',
    alcoholContent: '40% Alc./Vol. (80 Proof)',
    netContents: '750 mL',
    bottlerNameAddress: 'Glen Arden Imports, New York, NY',
    countryOfOrigin: 'Scotland',
    beverageType: 'spirits',
  },
  {
    colaNumber: '25-009766',
    brandName: 'SUMMIT RIDGE',
    classType: 'Straight Rye Whiskey',
    alcoholContent: '47% Alc./Vol. (94 Proof)',
    netContents: '750 mL',
    bottlerNameAddress: 'Summit Spirits, Denver, Colorado',
    beverageType: 'spirits',
  },
];

/** Pair each sample COLA with its matching label image filename. */
export const SAMPLE_LABEL_FILENAMES: Record<string, string> = {
  '25-001234': 'label_1_old_tom_spirits.png',
  '25-002301': 'label_2_stones_throw_wine.png',
  '25-003988': 'label_3_northwind_beer.png',
  '25-004102': 'label_4_cedar_sage_missing_warning.png',
  '25-005517': 'label_5_valley_crest_wine.png',
  '25-006023': 'label_6_iron_anchor_lager.png',
  '25-007840': 'label_7_bright_wave_seltzer.png',
  '25-008311': 'label_8_glen_arden_scotch.png',
  '25-009766': 'label_9_summit_peak_rye.png',
};
