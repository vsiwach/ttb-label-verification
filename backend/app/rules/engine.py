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
    "beer", "ale", "stout", "porter", "lager", "malt beverage",
    "malt beverages specialities", "malt beverages specialities - flavored",
    # Wine umbrellas
    "wine", "table wine", "table red wine", "table white wine", "rose wine",
    "table flavored wine", "sparkling wine", "sparkling wine/champagne",
    "dessert /port/sherry/(cooking) wine", "fortified wine",
    "honey based table wine", "cider",
    # Spirits umbrellas
    "distilled spirits", "spirits", "whisky", "whiskey",
    "whisky specialties", "vodka", "vodka specialties", "gin", "rum",
    "tequila", "tequila fb", "mezcal", "mezcal fb", "brandy", "liqueur",
    "other whisky", "other whisky (flavored)", "other specialties & proprietaries",
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


def _classify_brand(declared: str, extracted: str):
    """Brand-name comparison tuned for real-world stylistic realities.

    Compared to the generic classifier:
      - Case-only differences → 'match' (TTB-registered name in title case vs
        the same name printed in all caps is a stylistic, not substantive,
        difference). The PRD's STONE'S THROW-as-'likely' case is now also
        treated this way — both sides resolve via the same engine.
      - Common business suffixes are stripped before comparison
        (e.g. 'Suprema Imported Beer' ≡ 'Suprema').
      - Substantively different brands still produce 'flag'.
    """
    from .field_match import FieldVerdict, _strict_normalize, classify_field

    d_norm = _brand_normalize(declared)
    e_norm = _brand_normalize(extracted)

    if not extracted:
        return classify_field(declared, extracted)
    if d_norm and e_norm and d_norm == e_norm:
        return FieldVerdict(
            status="match",
            normalized_declared=d_norm,
            normalized_extracted=e_norm,
            similarity=1.0,
            note=None if _strict_normalize(declared) == _strict_normalize(extracted) else
                 "Brand name printed in different case / with different business suffix; same registered name.",
        )
    # Prefix containment: 'suprema' in 'suprema imported beer' or vice versa
    if d_norm and e_norm and (d_norm in e_norm or e_norm in d_norm):
        return FieldVerdict(
            status="likely",
            normalized_declared=d_norm,
            normalized_extracted=e_norm,
            similarity=0.9,
            note="Brand name appears as a shortened/extended form on the label; please verify.",
        )
    # Fall back to the generic classifier (handles similarity + flag).
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
            verdict = _classify_brand(declared, extracted_value)
        elif spec.label_name == "Country of origin":
            verdict = _classify_country_of_origin(declared, extracted_value)
        elif spec.label_name == "Class & type" and _is_umbrella_class(declared):
            # Form declared a taxonomy umbrella ('beer'); label printed a specific
            # designation. Any non-empty designation is consistent.
            from .field_match import FieldVerdict
            verdict = FieldVerdict(
                status="match",
                normalized_declared=declared.lower(),
                normalized_extracted=extracted_value.lower(),
                similarity=1.0,
                note="Form declared an umbrella class; label's specific designation is consistent.",
            )
        elif spec.label_name == "Alcohol content":
            # Compare numeric percent (within 0.1) — formats vary ("% Alc./Vol.",
            # "% ABV", "% by volume", "Proof") but the percentage is what matters.
            pd, pe = _abv_percent(declared), _abv_percent(extracted_value)
            if pd is not None and pe is not None and abs(pd - pe) <= 0.1:
                from .field_match import FieldVerdict
                verdict = FieldVerdict(
                    status="match",
                    normalized_declared=f"{pd}%", normalized_extracted=f"{pe}%",
                    similarity=1.0,
                )
            else:
                verdict = classify_field(declared, extracted_value)
        elif spec.label_name == "Net contents":
            # Real labels often print multi-unit displays ('12L 40.5 fl oz 2.53 pint');
            # COLA carries a single unit. Compare semantically when both parse.
            ml_d = parse_net_contents_to_ml(declared)
            ml_e = parse_net_contents_to_ml(extracted_value)
            if ml_d is not None and ml_e is not None and ml_d > 0:
                if abs(ml_d - ml_e) / max(ml_d, ml_e) <= 0.05:
                    # Numeric volumes within 5% — treat as match regardless of unit display.
                    from .field_match import FieldVerdict
                    verdict = FieldVerdict(
                        status="match",
                        normalized_declared=f"{ml_d:.0f} mL",
                        normalized_extracted=f"{ml_e:.0f} mL",
                        similarity=1.0,
                    )
                else:
                    verdict = classify_field(declared, extracted_value)
            else:
                verdict = classify_field(declared, extracted_value)
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

    # Government Warning analysis (16.21 / 16.22)
    container_ml = parse_net_contents_to_ml(app.netContents)
    gw = analyze_warning(
        detected_text=extracted.warning_text,
        present=extracted.warning_present,
        style=extracted.warning_style,
        container_ml=container_ml,
    )

    image_quality = ImageQuality(
        score=extracted.image_quality_score,
        legible=extracted.image_legible,
        note=extracted.image_quality_note,
    )

    return VerificationResult(fields=fields, governmentWarning=gw, imageQuality=image_quality)
