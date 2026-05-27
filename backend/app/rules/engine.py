"""verify(extracted, applicationData) -> VerificationResult.

This is what /api/verify calls after the extractor returns. It is pure and
synchronous — every match/likely/flag decision and every Government Warning
verdict happens here, with a regulation citation attached.
"""

from __future__ import annotations

from ..extractors.base import ExtractedLabel
from ..models import (
    ApplicationData,
    ImageQuality,
    VerificationField,
    VerificationResult,
)
from .citations import citation_for_field
from .field_match import classify_field
from .government_warning import analyze_warning
from .mandatory_fields import applies_to, declared_value
from .net_contents import parse_net_contents_to_ml


import re as _re

# COLA registry's class/type codes are taxonomy buckets ('beer', 'ale', 'table
# red wine'); the LABEL prints specific designations ('Czech-Style Pilsner',
# 'New Zealand Style Pilsner', 'Sonoma County Chardonnay'). TTB approves the
# COLA against the broader bucket so a label-side specific designation under
# a known umbrella is a match, not a flag.
_UMBRELLA_CLASSES = {
    # Beer/malt umbrellas
    "beer", "ale", "stout", "porter", "lager", "pilsner", "malt beverage",
    "malt beverages specialities", "malt beverages specialities - flavored",
    "ipa", "india pale ale",
    # Wine umbrellas
    "wine", "table wine", "table red wine", "table white wine", "rose wine",
    "table flavored wine", "sparkling wine", "sparkling wine/champagne",
    "dessert /port/sherry/(cooking) wine", "fortified wine",
    "honey based table wine", "cider", "perry", "mead",
    "grape wine", "fruit wine", "specialty wine",
    # Spirits umbrellas
    "distilled spirits", "spirits", "whisky", "whiskey",
    "whisky specialties", "whiskey specialties",
    "vodka", "vodka 80-89 proof", "vodka specialties",
    "gin", "rum", "agave spirits",
    "tequila", "tequila fb", "mezcal", "mezcal fb",
    "brandy", "cognac", "liqueur", "cordial", "schnapps",
    "other whisky", "other whisky (flavored)",
    "other specialties & proprietaries", "neutral spirits",
    "straight whisky", "straight whiskey", "bourbon whisky", "bourbon whiskey",
    "rye whisky", "rye whiskey",
    # Cider / RTD
    "hard cider", "fruit cider",
}

# A model confidence below this on a 'match' verdict promotes to 'likely' —
# the agent gets a "please confirm" rather than an unverified pass. Tuned for
# the cloud extractor which calibrates ~0.95 on confident reads and ~0.4–0.6
# on guesses.
LOW_CONFIDENCE_PROMOTE_THRESHOLD = 0.60


def _is_umbrella_class(declared: str) -> bool:
    return declared.strip().lower() in _UMBRELLA_CLASSES


def _abv_percent(s: str) -> float | None:
    """Pull the first percentage out of an alcohol-content string."""
    if not s:
        return None
    m = _re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", s)
    return float(m.group(1)) if m else None


# Per-beverage ABV tolerance (absolute % delta) — TTB allows variation
# between the stated and actual ABV in 27 CFR. Within tolerance the
# difference is informational (match); just outside is 'likely' (agent
# confirms); a substantive divergence is a flag.
# Source citations:
#   - Spirits 27 CFR 5.65(d): tolerance ±0.15% (we use a slightly wider
#     0.3 to absorb model-rounding from the label).
#   - Wine    27 CFR 4.36(b): ±1.0% for wines >14% ABV, ±1.5% for ≤14% ABV
#     (we use 0.5% to stay strict on consumer-facing reads).
#   - Malt    27 CFR 7.65: ±0.3% for beer (when stated).
_ABV_MATCH_TOLERANCE = {
    "spirits": 0.30,
    "wine":    0.50,
    "beer":    0.30,
    "malt":    0.30,
}
# Within this wider band we still consider it 'likely' (needs-confirm), not flag.
_ABV_LIKELY_TOLERANCE = {
    "spirits": 1.0,
    "wine":    1.5,
    "beer":    1.0,
    "malt":    1.0,
}


def _classify_abv(declared: str, extracted: str, beverage_type: str):
    """Numeric percent comparison with per-beverage tolerance."""
    from .field_match import FieldVerdict, classify_field

    pd, pe = _abv_percent(declared), _abv_percent(extracted)
    if pd is None or pe is None:
        return classify_field(declared, extracted)

    diff = abs(pd - pe)
    match_tol = _ABV_MATCH_TOLERANCE.get(beverage_type, 0.3)
    likely_tol = _ABV_LIKELY_TOLERANCE.get(beverage_type, 1.0)

    if diff <= match_tol:
        return FieldVerdict(
            status="match",
            normalized_declared=f"{pd}%", normalized_extracted=f"{pe}%",
            similarity=1.0,
        )
    if diff <= likely_tol:
        return FieldVerdict(
            status="likely",
            normalized_declared=f"{pd}%", normalized_extracted=f"{pe}%",
            similarity=0.9,
            note=f"ABV differs by {diff:.1f}% (declared {pd}% vs label {pe}%) — within agent-review tolerance.",
        )
    return FieldVerdict(
        status="flag",
        normalized_declared=f"{pd}%", normalized_extracted=f"{pe}%",
        similarity=0.0,
        note=f"ABV differs by {diff:.1f}% — declared {pd}% vs label {pe}% — beyond TTB tolerance for {beverage_type}.",
    )


# Common business-name suffixes / qualifiers labels routinely drop or add.
# When one side is the same brand minus one of these, treat as match.
_BRAND_NOISE_TOKENS = {
    "imported beer", "imported wine", "imported", "import",
    "brewing co", "brewing company", "brewing", "brewery",
    "vineyard", "vineyards", "winery", "wineries", "cellars",
    "distillery", "distilleries", "distilling", "distillers",
    "spirits", "company", "co", "co.", "inc", "inc.", "ltd", "ltd.",
    "llc", "llp", "lp", "corp", "corp.", "corporation", "gmbh",
    "soc agr srl", "srl", "s.a.s. de c.v.", "s.a.", "s.a", "s.r.l.",
    "estate", "estates", "ranch", "farms", "farm", "cidery",
    "the",
}


def _brand_normalize(s: str) -> str:
    """Lowercase, strip diacritics/punctuation, collapse whitespace, drop common
    business-name suffix tokens like 'Imported Beer', 'LLC', 'Brewing Co'."""
    import re as _r
    import unicodedata as _u
    if not s:
        return ""
    s = _u.normalize("NFKD", s)
    s = "".join(ch for ch in s if not _u.combining(ch))
    s = s.lower()
    s = _r.sub(r"[^\w\s.]+", " ", s)
    s = _r.sub(r"\s+", " ", s).strip()
    # Iteratively strip trailing noise tokens
    changed = True
    while changed:
        changed = False
        for tok in sorted(_BRAND_NOISE_TOKENS, key=len, reverse=True):
            if s == tok:
                s = ""
                changed = True; break
            if s.endswith(" " + tok):
                s = s[:-(len(tok) + 1)].strip()
                changed = True; break
        # Also strip leading 'the '
        if s.startswith("the "):
            s = s[4:].strip(); changed = True
    return s


def _classify_brand(declared: str, extracted: str, *, product_name: str = ""):
    """Brand-name comparison tuned for real-world stylistic realities.

    Compared to the generic classifier:
      - Case-only differences → 'match' (TTB-registered name in title case vs
        the same name printed in all caps is a stylistic, not substantive,
        difference).
      - Common business suffixes are stripped before comparison
        (e.g. 'Suprema Imported Beer' ≡ 'Suprema').
      - **A match against the COLA form's Product/Fanciful Name also counts
        as match** — real labels often print the SKU/product more
        prominently than the registered brand. This is the single largest
        false-positive reducer on real artwork.
      - Substantively different brand AND product still produce 'flag'.
    """
    from .field_match import FieldVerdict, _strict_normalize, classify_field

    if not extracted:
        return classify_field(declared, extracted)

    e_norm = _brand_normalize(extracted)
    d_norm = _brand_normalize(declared)
    p_norm = _brand_normalize(product_name)

    # 1. Direct match against the registered brand.
    if d_norm and e_norm and d_norm == e_norm:
        return FieldVerdict(
            status="match", normalized_declared=d_norm, normalized_extracted=e_norm, similarity=1.0,
            note=None if _strict_normalize(declared) == _strict_normalize(extracted) else
                 "Brand name printed in different case / with different business suffix; same registered name.",
        )

    # 2. Match against the COLA form's Product/Fanciful Name (when supplied).
    if p_norm and e_norm and p_norm == e_norm:
        return FieldVerdict(
            status="match", normalized_declared=d_norm, normalized_extracted=e_norm, similarity=1.0,
            note=f"Label prints the Product/Fanciful Name (per COLA form) — registered brand is '{declared}'.",
        )

    # 3. Containment in either name: shortened/extended form (e.g. 'Suprema'
    # vs 'Suprema Imported Beer'; or label has product name containing brand).
    for cand_norm, cand_label in [(d_norm, "registered brand"), (p_norm, "product name")]:
        if cand_norm and e_norm and (cand_norm in e_norm or e_norm in cand_norm):
            return FieldVerdict(
                status="likely", normalized_declared=cand_norm, normalized_extracted=e_norm, similarity=0.9,
                note=f"Label brand appears as a shortened/extended form of the {cand_label}; please verify.",
            )

    # 4. Fall back to the generic classifier against the declared brand.
    return classify_field(declared, extracted)


# COO prefixes labels routinely use (English + common languages we see in the
# COLA Cloud sample: French, Spanish, Italian, German, Portuguese).
_COO_PREFIXES = (
    # English
    "product of ", "produce of ", "imported from ", "made in ",
    "bottled in ", "distilled in ", "produced in ", "vintaged in ",
    # French
    "produit de ", "produit en ", "vin de ",
    # Spanish
    "hecho en ", "producto de ", "elaborado en ", "vino de ",
    "embotellado en ",
    # Italian
    "prodotto in ", "imbottigliato in ", "vino di ",
    # German
    "erzeugnis aus ", "produkt aus ", "abgefullt in ",
    # Portuguese
    "produto de ", "feito em ",
)


def _normalize_country_of_origin(extracted: str) -> str:
    """Strip common 'Product of X' prefixes (English + common languages) so
    'PRODUIT DE FRANCE', 'HECHO EN MEXICO', 'PRODOTTO IN ITALIA' all reduce
    to just the country name.

    Real labels frequently print DUAL-LANGUAGE displays like
    'PRODUIT DE FRANCE PRODUCT OF FRANCE'. We strip the first matching prefix,
    then again on the remainder until no prefix matches.
    """
    if not extracted:
        return extracted
    out = extracted.strip()
    # Strip up to 3 layers of prefix (for dual / triple language displays).
    for _ in range(3):
        low = out.lower()
        changed = False
        for prefix in _COO_PREFIXES:
            if low.startswith(prefix):
                out = out[len(prefix):].strip()
                changed = True
                break
        if not changed:
            break
    return out


_BOTTLER_SUFFIX_TOKENS = {
    # Business-entity suffixes that appear anywhere on a bottler line and
    # carry no semantic weight for matching purposes. Stripped from BOTH
    # sides before token-subset comparison.
    "llc", "l.l.c.", "l.l.c", "inc", "inc.", "ltd", "ltd.",
    "corp", "corp.", "corporation", "co", "co.", "company",
    "gmbh", "srl", "s.r.l.", "sa", "s.a.", "s.a", "sas",
    "s.a.s.", "s.a.s", "de", "c.v.", "cv",
}

# US state name ↔ 2-letter abbreviation (lowercase). Bottler addresses
# routinely declared one way and printed the other (declared "Illinois"
# vs label "IL"); both should match.
_STATE_ABBR = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn",
    "mississippi": "ms", "missouri": "mo", "montana": "mt", "nebraska": "ne",
    "nevada": "nv", "new hampshire": "nh", "new jersey": "nj",
    "new mexico": "nm", "new york": "ny", "north carolina": "nc",
    "north dakota": "nd", "ohio": "oh", "oklahoma": "ok", "oregon": "or",
    "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa",
    "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
}


# Regex stripping common business-entity suffixes WHEREVER they appear,
# with or without dots. Matches "LLC", "L.L.C.", "L.L.C", "INC", "INC.",
# "S.A.S. DE C.V." etc. Applied before the generic punctuation-strip so
# the dotted variants don't decompose into single-letter tokens that
# would survive the suffix filter.
_BIZ_SUFFIX_RE = __import__("re").compile(
    r"\b(?:"
    r"l\.?\s*l\.?\s*c\.?|"
    r"l\.?\s*l\.?\s*p\.?|"
    r"l\.?\s*p\.?|"
    r"inc\.?|"
    r"ltd\.?|"
    r"corp(?:oration)?\.?|"
    r"co(?:mpany)?\.?|"
    r"gmbh|"
    r"s\.?\s*a\.?\s*s\.?(?:\s*de\s*c\.?\s*v\.?)?|"
    r"s\.?\s*r\.?\s*l\.?|"
    r"s\.?\s*a\.?"
    r")\b",
    flags=__import__("re").IGNORECASE,
)


def _bottler_tokens(s: str) -> set[str]:
    """Tokenize a bottler line into a set of comparable words.

    Business suffixes are removed (whether dotted "L.L.C." or not),
    multi-word state names collapse to their 2-letter abbreviation,
    leftover punctuation is dropped. The output is a SET so comparisons
    are order- and duplicate-insensitive. A street number like "1144"
    stays a token — addresses that share only the city/state still
    match because the city+state are the pieces the label actually
    has to show under 27 CFR.
    """
    import re as _r
    if not s:
        return set()
    # Lowercase + diacritic strip first (mirror _brand_normalize start)
    import unicodedata as _u
    norm = _u.normalize("NFKD", s)
    norm = "".join(ch for ch in norm if not _u.combining(ch)).lower()
    # Strip business-entity suffixes (with optional dots) BEFORE general
    # punctuation removal — otherwise "l.l.c." decomposes into ["l","l","c"]
    # which the suffix-set filter doesn't recognize.
    norm = _BIZ_SUFFIX_RE.sub(" ", norm)
    # Collapse multi-word state names to their abbreviation.
    for full, abbr in _STATE_ABBR.items():
        norm = _r.sub(rf"\b{full}\b", abbr, norm)
    # Drop punctuation, then split on whitespace.
    norm = _r.sub(r"[^\w\s]+", " ", norm)
    toks = set(
        t for t in norm.split()
        if t and t not in _BOTTLER_SUFFIX_TOKENS and len(t) > 1
    )
    return toks


def _classify_bottler(declared: str, extracted: str, *, brand_name: str = ""):
    """Bottler/producer name & address — permissive.

    Real bottler lines printed on labels routinely contain MUCH more than
    the COLA form's bottler field. Typical patterns:
      declared:  'Half Acre, Illinois'
      extracted: 'BREWED BY HALF ACRE IN CHICAGO, ILLINOIS'

      declared:  'Moonridge Vineyard Santa Rosa, CA'
      extracted: 'MOONRIDGE VINEYARD LLC, Santa Rosa, CA'

      declared:  'World Sake Imports 1144 Tenth Ave Suite 401 Honolulu HI'
      extracted: 'WORLD SAKE IMPORTS L.L.C., Honolulu, HI'

    TTB doesn't reject for extra detail on the printed bottler line; the
    requirement is that a bottler/producer name + address actually appear.
    Three-stage match (cascading from most strict to most lenient):
      1. Substring containment of fully-normalized strings → match
      2. Brand-name containment in extracted → match
      3. Token-subset (city+state+entity-name tokens line up either
         direction, business suffixes stripped) → match
    Otherwise generic similarity — substantively different entities still flag.
    """
    from .field_match import FieldVerdict, _strict_normalize, classify_field

    if not extracted:
        return classify_field(declared, extracted)

    e_norm = _brand_normalize(extracted)
    d_norm = _brand_normalize(declared)
    b_norm = _brand_normalize(brand_name)

    # 1. Substring containment of normalized strings → match.
    if d_norm and (d_norm in e_norm or e_norm in d_norm):
        return FieldVerdict(
            status="match", normalized_declared=d_norm, normalized_extracted=e_norm,
            similarity=1.0,
            note=None if _strict_normalize(declared) == _strict_normalize(extracted) else
                 "Bottler line on the label contains the registered bottler with additional address detail.",
        )

    # 2. Brand-name containment in extracted (TTB-registered bottler often
    # IS the brewery; printed line spells it out with city/plant info).
    if b_norm and b_norm in e_norm:
        return FieldVerdict(
            status="match", normalized_declared=d_norm, normalized_extracted=e_norm,
            similarity=0.95,
            note=f"Label's bottler line references the registered brand '{brand_name}'.",
        )

    # 3. Token-subset match after business-suffix strip + state-abbr fold.
    # Handles "Moonridge Vineyard Santa Rosa CA" vs "Moonridge Vineyard
    # LLC, Santa Rosa, CA" (extra LLC) and "World Sake Imports 1144 Tenth
    # Ave Suite 401 Honolulu HI" vs "World Sake Imports L.L.C., Honolulu,
    # HI" (declared is a superset of extracted with street detail). At
    # least 2 shared tokens prevents trivial single-word coincidences.
    d_tok = _bottler_tokens(declared)
    e_tok = _bottler_tokens(extracted)
    if d_tok and e_tok:
        shared = d_tok & e_tok
        smaller = min(d_tok, e_tok, key=len)
        if shared and shared == smaller and len(shared) >= 2:
            return FieldVerdict(
                status="match", normalized_declared=d_norm, normalized_extracted=e_norm,
                similarity=0.9,
                note=(
                    "Bottler tokens line up (business-entity suffix and "
                    "street-address detail differ but the core name + "
                    "city/state match)."
                ),
            )

    # Otherwise generic comparison — different business entity should still flag.
    return classify_field(declared, extracted)


# Standard-fill volumes (mL) per 27 CFR 4.72 (wine), 5.47a (spirits),
# 7.27 (malt). A label printed within ±2% of these is exactly the
# regulated fill; this lets us be stricter than the generic ±5% tolerance
# when the declared volume is a standard fill, because real labels at
# 750 mL hit 750 mL exactly (the model occasionally reads 745 or 752 due
# to OCR — within ±2% is fine).
_STANDARD_FILLS_ML = (
    50, 100, 187, 200, 250, 330, 355, 375, 500, 700, 720, 750,
    1000, 1500, 1750, 1893, 3000,  # mL standards
    # Beer fluid-ounce standards:
    340, 355, 473, 568, 650, 710, 946,
    # Spirits half-gallon, gallon (rarely on labels but possible):
    1893, 3785,
)


def _is_standard_fill(ml: float) -> bool:
    return any(abs(ml - s) / s <= 0.03 for s in _STANDARD_FILLS_ML)


def _classify_net_contents(declared: str, extracted: str):
    """Net contents — semantic mL comparison with a graduated tolerance:
      - within 2% of declared, AND the declared is a standard fill → match
        (sharp tolerance on regulated container sizes)
      - within 5% otherwise → match (handles multi-unit print + rounding)
      - within 10% → likely (border-tolerance; agent confirms)
      - else → flag (substantive content difference, e.g. 750 mL vs 500 mL)
    """
    from .field_match import FieldVerdict, classify_field

    ml_d = parse_net_contents_to_ml(declared)
    ml_e = parse_net_contents_to_ml(extracted)
    if ml_d is None or ml_e is None or ml_d <= 0:
        return classify_field(declared, extracted)

    delta = abs(ml_d - ml_e) / max(ml_d, ml_e)
    standard = _is_standard_fill(ml_d)
    if delta <= (0.02 if standard else 0.05):
        return FieldVerdict(
            status="match",
            normalized_declared=f"{ml_d:.0f} mL", normalized_extracted=f"{ml_e:.0f} mL",
            similarity=1.0,
        )
    if delta <= 0.10:
        return FieldVerdict(
            status="likely",
            normalized_declared=f"{ml_d:.0f} mL", normalized_extracted=f"{ml_e:.0f} mL",
            similarity=0.9,
            note=f"Net contents differs by {delta:.1%} ({ml_d:.0f} mL declared vs {ml_e:.0f} mL on label) — within border-tolerance, agent confirms.",
        )
    return FieldVerdict(
        status="flag",
        normalized_declared=f"{ml_d:.0f} mL", normalized_extracted=f"{ml_e:.0f} mL",
        similarity=0.0,
        note=f"Net contents differs by {delta:.1%}; substantive content difference.",
    )


def _classify_country_of_origin(declared: str, extracted: str):
    """COO comparison tolerant of: foreign-language prefixes, dual-language
    displays, and the printed country appearing anywhere in the extracted
    text after noise is stripped.

    Examples that should be 'match':
      declared='france'  extracted='PRODUIT DE FRANCE PRODUCT OF FRANCE'
      declared='mexico'  extracted='HECHO EN MEXICO'
      declared='italy'   extracted='PRODOTTO IN ITALIA'   (italia ≡ italy?)
    """
    from .field_match import FieldVerdict, classify_field

    if not extracted:
        return classify_field(declared, extracted)

    # Country name normalization (English) — handles native-language forms
    # the engine commonly sees on imported labels.
    country_aliases = {
        "italy":   {"italy", "italia"},
        "france":  {"france"},
        "spain":   {"spain", "espana", "españa"},
        "germany": {"germany", "deutschland"},
        "mexico":  {"mexico", "méxico"},
        "portugal":{"portugal"},
        "argentina":{"argentina"},
        "chile":   {"chile"},
        "scotland":{"scotland"},
        "ireland": {"ireland", "eire"},
        "japan":   {"japan", "nippon"},
    }
    d_low = declared.strip().lower()
    target_words = country_aliases.get(d_low, {d_low})

    # Strip prefixes, then tokenize the result.
    stripped = _normalize_country_of_origin(extracted).lower()
    # Also strip prefix tokens that may not be at position 0 (dual-language).
    for prefix in _COO_PREFIXES:
        if prefix.strip() in stripped:
            stripped = stripped.replace(prefix.strip(), " ")
    # Word-level membership check.
    import re as _r
    tokens = set(_r.findall(r"[a-zA-Záéíóúñü]+", stripped))
    if target_words & tokens:
        return FieldVerdict(
            status="match",
            normalized_declared=d_low,
            normalized_extracted=" ".join(sorted(tokens)),
            similarity=1.0,
            note=None if d_low in tokens else f"Country name appears in '{extracted.strip()[:60]}' after prefix strip.",
        )
    # Fall through to similarity / containment via the generic classifier.
    return classify_field(declared.title(), _normalize_country_of_origin(extracted).title())


# Class/type tokens that indicate a malt beverage contains added nonbeverage
# flavors and therefore (per 27 CFR 7.63) requires an ABV statement.
_FLAVORED_MALT_TOKENS = (
    "seltzer", "hard seltzer", "flavored malt", "flavored beer",
    "fruit beer", "spiked", "ready to drink", "rtd",
)


def _looks_like_flavored_malt(app: ApplicationData) -> bool:
    ct = (app.classType or "").lower()
    return any(t in ct for t in _FLAVORED_MALT_TOKENS)


def _classify_class_type(declared: str, extracted: str):
    """Class/type comparison tolerant of finishing/style descriptors.

    Real labels routinely add descriptive copy after the registered class:
      declared:  'Kentucky Straight Bourbon Whiskey'
      extracted: 'KENTUCKY STRAIGHT BOURBON WHISKEY FINISHED WITH TOASTED MAPLE WOOD'

      declared:  'Sonoma County Chardonnay'
      extracted: 'Sonoma County Chardonnay — Reserve, Estate Bottled'

    The added words ('finished with...', 'reserve', 'estate bottled', etc.)
    don't change the class/type designation; they're marketing detail.
    Whenever the declared class appears as a substring of the extracted
    text (or vice versa), treat as match. The umbrella-class rule
    (form says 'beer', label says 'Pilsner') is the same pattern,
    handled here too.
    """
    from .field_match import FieldVerdict, _strict_normalize, classify_field

    if not extracted:
        return classify_field(declared, extracted)

    d_low = declared.strip().lower()
    e_low = extracted.strip().lower()

    # Exact match (case-insensitive) — common case. Return MATCH directly
    # instead of round-tripping through classify_field, which would have
    # re-checked with case-preserving normalization and demoted a
    # purely-casing-different pair (e.g. "table white wine" on the form
    # vs "TABLE WHITE WINE" on the label) to "likely" with a misleading
    # "casing differs" note. Class & type casing parity is not a TTB
    # requirement, so this is unambiguously a full match.
    if d_low == e_low:
        return FieldVerdict(
            status="match",
            normalized_declared=d_low,
            normalized_extracted=e_low,
            similarity=1.0,
        )

    # Umbrella class declared, specific designation on label → match.
    # (form says 'beer', label says 'India Pale Ale')
    if _is_umbrella_class(declared):
        return FieldVerdict(
            status="match",
            normalized_declared=d_low,
            normalized_extracted=e_low,
            similarity=1.0,
            note="Form declared an umbrella class; label's specific designation is consistent.",
        )

    # Containment: declared class appears in the label's longer phrase
    # (or vice versa). Catches finishing/style descriptors and reserve
    # designations that don't change the class.
    if d_low in e_low or e_low in d_low:
        return FieldVerdict(
            status="match",
            normalized_declared=d_low,
            normalized_extracted=e_low,
            similarity=0.95,
            note=None if _strict_normalize(declared) == _strict_normalize(extracted) else
                 "Label adds descriptive detail to the registered class; designation is consistent.",
        )

    # Otherwise generic similarity comparison — substantively different
    # designations still flag.
    return classify_field(declared, extracted)


def verify(
    extracted: ExtractedLabel,
    app: ApplicationData,
    *,
    contains_added_flavors: bool | None = None,
) -> VerificationResult:
    """Turn raw model observations into the public VerificationResult.

    contains_added_flavors: explicit override; if None, auto-detect from the
    application's class type so the rules engine catches flavored-malt /
    seltzer products without callers having to flag them.
    """

    if contains_added_flavors is None:
        contains_added_flavors = _looks_like_flavored_malt(app)
    cite = citation_for_field(app.beverageType)
    specs = applies_to(app, contains_added_flavors=contains_added_flavors)

    fields: list[VerificationField] = []
    for spec in specs:
        declared = declared_value(app, spec)
        extracted_field = extracted.fields.get(spec.label_name)

        if extracted_field is None or not extracted_field.value:
            # Field not visible on this image. Real COLAs are multi-image —
            # ABV / net contents / bottler are often on a different panel from
            # the Government Warning. We mark this as 'likely' (route to
            # needs-confirm) with a clear note rather than a hard flag.
            fields.append(VerificationField(
                fieldName=spec.label_name,
                declaredValue=declared,
                extractedValue="",
                status="likely",
                confidence=extracted_field.confidence if extracted_field else 0.0,
                regulationCite=cite,
                note=f"Could not verify on this label image; may be on another panel ({cite}).",
            ))
            continue

        if not declared:
            # Application omitted this field (e.g. COLA form lacks bottler line on
            # some exports). The label content is shown for the agent; treat as
            # match for bucketing purposes — the form-level check happens elsewhere.
            fields.append(VerificationField(
                fieldName=spec.label_name,
                declaredValue="",
                extractedValue=extracted_field.value,
                status="match",
                confidence=extracted_field.confidence,
                regulationCite=cite,
                note="Application did not declare this field; label content shown for review.",
            ))
            continue

        # Per-field normalization for real-world realities the COLA form doesn't capture:
        extracted_value = extracted_field.value
        if spec.label_name == "Brand name":
            # Accept a match against EITHER the registered brand or the
            # COLA form's Product/Fanciful Name. Labels routinely print the
            # SKU/product name more prominently than the brewery brand.
            verdict = _classify_brand(declared, extracted_value, product_name=app.productName or "")
        elif spec.label_name == "Country of origin":
            verdict = _classify_country_of_origin(declared, extracted_value)
        elif spec.label_name == "Class & type":
            verdict = _classify_class_type(declared, extracted_value)
        elif spec.label_name == "Alcohol content":
            # Per-beverage ABV tolerance — within 27 CFR-stated tolerance is match,
            # outside-but-close is 'likely' (needs-confirm), substantive is flag.
            verdict = _classify_abv(declared, extracted_value, app.beverageType)
        elif spec.label_name == "Net contents":
            # Graduated tolerance: 2% on standard fills, 5% otherwise, 10% border.
            verdict = _classify_net_contents(declared, extracted_value)
        elif spec.label_name == "Bottler name/address":
            # Permissive — extracted line containing declared bottler OR brand → match.
            verdict = _classify_bottler(declared, extracted_value, brand_name=app.brandName)
        else:
            verdict = classify_field(declared, extracted_value)

        # Conservative routing: a 'match' produced from a low-confidence
        # extraction is downgraded to 'likely' so the agent confirms. This
        # protects against the model 'matching' because it confidently read
        # the wrong tokens (e.g. brand vs product name, deposit code vs ABV).
        status = verdict.status
        note = verdict.note
        if status == "match" and extracted_field.confidence < LOW_CONFIDENCE_PROMOTE_THRESHOLD:
            status = "likely"
            note = (
                f"Low extractor confidence ({extracted_field.confidence:.2f}); please confirm."
                + (f" — {verdict.note}" if verdict.note else "")
            )

        fields.append(VerificationField(
            fieldName=spec.label_name,
            declaredValue=declared,
            extractedValue=extracted_field.value,  # show what was printed
            status=status,
            confidence=extracted_field.confidence,
            regulationCite=cite,
            note=note,
        ))

    # Government Warning analysis (16.21 / 16.22). Pass the image DPI
    # through so the type-size check can compute mm when both DPI and
    # warning bbox are available.
    container_ml = parse_net_contents_to_ml(app.netContents)
    gw = analyze_warning(
        detected_text=extracted.warning_text,
        present=extracted.warning_present,
        style=extracted.warning_style,
        container_ml=container_ml,
        image_dpi=extracted.image_dpi,
    )

    image_quality = ImageQuality(
        score=extracted.image_quality_score,
        legible=extracted.image_legible,
        note=extracted.image_quality_note,
    )

    return VerificationResult(fields=fields, governmentWarning=gw, imageQuality=image_quality)
