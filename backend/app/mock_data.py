"""Mock fixtures for INFERENCE_MODE=mock.

These mirror src/api/mockData.ts so the frontend sees the same three demo
scenarios when it points at this backend. Citations have been upgraded to the
post-2020 27 CFR numbering (spirits §5.63, wine §4.32, malt/beer §7.63,
warning §16.21/§16.22) per the handoff doc.
"""

from urllib.parse import quote

from .constants import VERBATIM_GOVERNMENT_WARNING, WARNING_REGULATION
from .models import (
    ApplicationData,
    GovernmentWarningAnalysis,
    ImageQuality,
    VerificationField,
    VerificationResult,
    WarningDeviation,
)


def svg_placeholder(label: str = "", w: int = 120, h: int = 80, bg: str = "#eef1f7", fg: str = "#1a4480") -> str:
    """Inline SVG data URL — matches svgPlaceholder() in src/api/mockData.ts."""
    safe = "".join(ch for ch in label if ch not in "<>&")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
        f'<rect width="{w}" height="{h}" fill="{bg}"/>'
        f'<text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" '
        f'font-family="ui-monospace,SF Mono,Consolas,monospace" font-size="11" fill="{fg}">{safe}</text>'
        f"</svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg, safe="")


SAVED_APPLICATIONS: list[ApplicationData] = [
    ApplicationData(
        colaNumber="25-001234",
        brandName="OLD TOM DISTILLERY",
        classType="Kentucky Straight Bourbon Whiskey",
        alcoholContent="45% Alc./Vol. (90 Proof)",
        netContents="750 mL",
        bottlerNameAddress="Old Tom Distillery, Frankfort, Kentucky",
        beverageType="spirits",
    ),
    ApplicationData(
        colaNumber="25-002301",
        brandName="STONE'S THROW",
        classType="California Red Table Wine",
        alcoholContent="13.5% Alc./Vol.",
        netContents="750 mL",
        bottlerNameAddress="Stone's Throw Cellars, Sonoma, California",
        beverageType="wine",
    ),
    ApplicationData(
        colaNumber="25-003988",
        brandName="NORTHWIND BREWING",
        classType="India Pale Ale",
        alcoholContent="6.8% Alc./Vol.",
        netContents="12 FL OZ",
        bottlerNameAddress="Northwind Brewing Co., Bend, Oregon",
        beverageType="beer",
    ),
]


# Scenario A — OLD TOM DISTILLERY, all matches
SCENARIO_A = VerificationResult(
    fields=[
        VerificationField(fieldName="Brand name",          declaredValue="OLD TOM DISTILLERY",
                          extractedValue="OLD TOM DISTILLERY", status="match", confidence=0.99,
                          regulationCite="27 CFR 5.63",
                          evidenceCropUrl=svg_placeholder("brand crop", bg="#f6efe1", fg="#7a5300")),
        VerificationField(fieldName="Class & type",        declaredValue="Kentucky Straight Bourbon Whiskey",
                          extractedValue="Kentucky Straight Bourbon Whiskey", status="match", confidence=0.97,
                          regulationCite="27 CFR 5.63",
                          evidenceCropUrl=svg_placeholder("class crop", bg="#f0e9d8", fg="#5a3b00")),
        VerificationField(fieldName="Alcohol content",     declaredValue="45% Alc./Vol. (90 Proof)",
                          extractedValue="45% Alc./Vol. (90 Proof)", status="match", confidence=0.96,
                          regulationCite="27 CFR 5.63",
                          evidenceCropUrl=svg_placeholder("ABV crop")),
        VerificationField(fieldName="Net contents",        declaredValue="750 mL",
                          extractedValue="750 mL", status="match", confidence=0.99,
                          regulationCite="27 CFR 5.63",
                          evidenceCropUrl=svg_placeholder("net qty crop")),
        VerificationField(fieldName="Bottler name/address", declaredValue="Old Tom Distillery, Frankfort, Kentucky",
                          extractedValue="Old Tom Distillery, Frankfort, KY", status="match", confidence=0.95,
                          regulationCite="27 CFR 5.63",
                          evidenceCropUrl=svg_placeholder("bottler crop")),
    ],
    governmentWarning=GovernmentWarningAnalysis(
        present=True, verbatimMatch=True, casingBoldOk=True, fontSizeOk=True,
        contrastOk=True, separateAndApart=True,
        detectedText=VERBATIM_GOVERNMENT_WARNING,
        deviations=[],
        regulation=WARNING_REGULATION,  # type: ignore[arg-type]
    ),
    imageQuality=ImageQuality(score=0.92, legible=True, note="Sharp; even lighting."),
)


# Scenario B — STONE'S THROW, casing near-match + net-contents flag
SCENARIO_B = VerificationResult(
    fields=[
        VerificationField(fieldName="Brand name",          declaredValue="STONE'S THROW",
                          extractedValue="Stone's Throw", status="likely", confidence=0.88,
                          regulationCite="27 CFR 4.32",
                          note="Casing differs from the application. Visual brand otherwise matches.",
                          evidenceCropUrl=svg_placeholder("brand crop", bg="#fff5dc", fg="#7a4a00")),
        VerificationField(fieldName="Class & type",        declaredValue="California Red Table Wine",
                          extractedValue="California Red Table Wine", status="match", confidence=0.96,
                          regulationCite="27 CFR 4.32",
                          evidenceCropUrl=svg_placeholder("class crop")),
        VerificationField(fieldName="Alcohol content",     declaredValue="13.5% Alc./Vol.",
                          extractedValue="13.5% Alc./Vol.", status="match", confidence=0.95,
                          regulationCite="27 CFR 4.32",
                          evidenceCropUrl=svg_placeholder("ABV crop")),
        VerificationField(fieldName="Net contents",        declaredValue="750 mL",
                          extractedValue="700 mL", status="flag", confidence=0.97,
                          regulationCite="27 CFR 4.32",
                          note="Net contents on the label does not match the application. Possible mislabel.",
                          evidenceCropUrl=svg_placeholder("net qty", bg="#f7dfd5", fg="#8a1a00")),
        VerificationField(fieldName="Bottler name/address", declaredValue="Stone's Throw Cellars, Sonoma, California",
                          extractedValue="Stone's Throw Cellars, Sonoma, CA", status="match", confidence=0.94,
                          regulationCite="27 CFR 4.32",
                          evidenceCropUrl=svg_placeholder("bottler crop")),
    ],
    governmentWarning=GovernmentWarningAnalysis(
        present=True, verbatimMatch=True, casingBoldOk=True, fontSizeOk=True,
        contrastOk=True, separateAndApart=True,
        detectedText=VERBATIM_GOVERNMENT_WARNING,
        deviations=[],
        regulation=WARNING_REGULATION,  # type: ignore[arg-type]
    ),
    imageQuality=ImageQuality(score=0.86, legible=True),
)


# Scenario C — NORTHWIND BREWING with a Title-Case + paraphrased + small-type warning
SCENARIO_C_WARNING_TEXT = (
    "Government Warning: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Drinking alcoholic beverages impairs your ability to drive a car or operate "
    "machinery and may cause health problems."
)

SCENARIO_C = VerificationResult(
    fields=[
        VerificationField(fieldName="Brand name",          declaredValue="NORTHWIND BREWING",
                          extractedValue="NORTHWIND BREWING", status="match", confidence=0.98,
                          regulationCite="27 CFR 7.63",
                          evidenceCropUrl=svg_placeholder("brand crop")),
        VerificationField(fieldName="Class & type",        declaredValue="India Pale Ale",
                          extractedValue="India Pale Ale", status="match", confidence=0.95,
                          regulationCite="27 CFR 7.63",
                          evidenceCropUrl=svg_placeholder("class crop")),
        VerificationField(fieldName="Net contents",        declaredValue="12 FL OZ",
                          extractedValue="12 FL. OZ.", status="likely", confidence=0.91,
                          regulationCite="27 CFR 7.63",
                          note='Punctuation differs ("FL. OZ." vs "FL OZ"). Equivalent.',
                          evidenceCropUrl=svg_placeholder("net qty crop")),
        VerificationField(fieldName="Bottler name/address", declaredValue="Northwind Brewing Co., Bend, Oregon",
                          extractedValue="Northwind Brewing Co., Bend, OR", status="match", confidence=0.93,
                          regulationCite="27 CFR 7.63",
                          evidenceCropUrl=svg_placeholder("bottler crop")),
    ],
    governmentWarning=GovernmentWarningAnalysis(
        present=True, verbatimMatch=False, casingBoldOk=False, fontSizeOk=False,
        contrastOk=True, separateAndApart=True,
        detectedText=SCENARIO_C_WARNING_TEXT,
        deviations=[
            WarningDeviation(type="casing",   message='"GOVERNMENT WARNING" must be all capitals and bold; detected title case.'),
            WarningDeviation(type="wording",  message="Statement wording does not match the required verbatim text."),
            WarningDeviation(type="fontSize", message="Warning text appears below the minimum type size for this container."),
        ],
        regulation=WARNING_REGULATION,  # type: ignore[arg-type]
    ),
    imageQuality=ImageQuality(score=0.79, legible=True, note="Warning band area is lower-resolution than the rest of the label."),
)


SCENARIOS: dict[str, VerificationResult] = {"A": SCENARIO_A, "B": SCENARIO_B, "C": SCENARIO_C}


def pick_scenario(app: ApplicationData | None) -> VerificationResult:
    """Brand-name heuristic identical to pickScenario() in src/api/client.ts."""
    if app is None:
        return SCENARIO_A
    brand = (app.brandName or "").upper()
    if "STONE" in brand:
        return SCENARIO_B
    if "NORTHWIND" in brand:
        return SCENARIO_C
    return SCENARIO_A


def thumb_for(scenario_key: str) -> str:
    name = {
        "A": "OLD",
        "B": "STONE'S",
        "C": "NORTHWIND",
    }.get(scenario_key, "label")
    return svg_placeholder(name, w=120, h=160)
