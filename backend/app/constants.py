"""Project-wide constants. These mirror values in src/api/types.ts and must
stay byte-identical so the frontend contract holds."""

# Verbatim Government Warning text (27 CFR 16.21). Must equal
# VERBATIM_GOVERNMENT_WARNING in src/api/types.ts character-for-character.
VERBATIM_GOVERNMENT_WARNING: str = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

WARNING_REGULATION: str = "27 CFR 16.21/16.22"
