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
