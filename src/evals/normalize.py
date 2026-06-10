"""Normalization + fuzzy/value matching primitives for the eval harness.

Open free-text fields (indication, therapeutic_area, geography, subject, ...) are
compared after **normalization + small domain synonym expansion**, then by stdlib
``difflib`` similarity — no third-party fuzzy dependency in v1 (escalate to
``rapidfuzz`` only if difflib proves too weak; see ``docs/HANDOFF.md``). Closed
enums are compared by exact match elsewhere; this module never touches them.

Three concerns live here:

1. **Text** — ``canonical_term`` (lowercase, depunctuate, British/American fold,
   abbrev/phrase expansion) and ``similarity`` / ``fuzzy_match`` over it.
2. **Asset slugs** — ``slug`` mirrors ``extraction.extractor._slug`` so a golden
   identifier ("VAY736") slugs to the same token a fact's ``asset_id`` already is
   ("vay736"). Parity is asserted in tests.
3. **Value scale** — ``to_base`` / ``values_match`` normalize "1.3 billion" and
   "1305 million" to a common base before comparing (dimension-gated, 2% rel-tol).
"""

import difflib
import re

# Approved fuzzy thresholds (docs/HANDOFF.md): >=0.90 match; 0.80-0.90 review band
# (where an LLM judge would later arbitrate); <0.80 miss.
FUZZY_MATCH = 0.90
FUZZY_REVIEW = 0.80

# British -> American spelling fold, applied token-wise after depunctuation.
_SPELLING = {
    "tumour": "tumor", "oedema": "edema", "paediatric": "pediatric",
    "haemolytic": "hemolytic", "haematological": "hematological", "anaemia": "anemia",
    "leukaemia": "leukemia", "coeliac": "celiac", "oesophageal": "esophageal",
    "fibrosis": "fibrosis",
}

# Abbreviation / phrase -> canonical phrase, in *post-normalization* form
# (lowercased, depunctuated: "IgA nephropathy" -> "iga nephropathy", "ex-US" -> "ex us").
_ALIASES = {
    # indications
    "uc": "ulcerative colitis",
    "hs": "hidradenitis suppurativa",
    "sle": "systemic lupus erythematosus",
    "itp": "immune thrombocytopenia",
    "waiha": "warm autoimmune hemolytic anemia",
    "aiha": "autoimmune hemolytic anemia",
    "iga nephropathy": "immunoglobulin a nephropathy",
    "igan": "immunoglobulin a nephropathy",
    "rcc": "renal cell carcinoma",
    "hcc": "hepatocellular carcinoma",
    "dmd": "duchenne muscular dystrophy",
    "msa": "multiple system atrophy",
    "cttp": "congenital thrombotic thrombocytopenic purpura",
    "nt1": "narcolepsy type 1",
    "hl": "hodgkin lymphoma",
    "cll": "chronic lymphocytic leukemia",
    "psc": "primary sclerosing cholangitis",
    # modality
    "mab": "monoclonal antibody",
    "adc": "antibody drug conjugate",
    # therapeutic area
    "gi": "gastroenterology",
    # geography
    "worldwide": "global",
    "united states": "us",
    "u s": "us",
    "u s a": "us",
    "ex us": "ex us",
    "europe": "eu",
    "china": "cn",
    "prc": "cn",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")
_WS_RE = re.compile(r"\s+")


def slug(name: str) -> str:
    """Asset slug — MUST mirror ``extraction.extractor._slug`` (parity test covers it)."""
    return _SLUG_RE.sub("-", name.strip().lower()).strip("-") or "unknown"


def normalize_text(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace, fold British spelling."""
    s = _PUNCT_RE.sub(" ", text.lower())
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return ""
    return " ".join(_SPELLING.get(tok, tok) for tok in s.split())


def canonical_term(text: str | None) -> str:
    """Normalize + expand abbreviations/phrases to a canonical comparison string.

    Whole-string aliases win first (so "IgAN" -> the full phrase); otherwise
    multi-word alias phrases are replaced where they occur, then single-token
    abbreviations. Idempotent on already-canonical input.
    """
    if not text:
        return ""
    s = normalize_text(text)
    if s in _ALIASES:
        return _ALIASES[s]
    # phrase replacements (longest first to avoid partial shadowing)
    for phrase in sorted((k for k in _ALIASES if " " in k), key=len, reverse=True):
        s = re.sub(rf"\b{re.escape(phrase)}\b", _ALIASES[phrase], s)
    # single-token abbreviations
    s = " ".join(_ALIASES.get(tok, tok) if " " not in _ALIASES.get(tok, tok) else tok
                 for tok in s.split())
    return _WS_RE.sub(" ", s).strip()


def similarity(a: str | None, b: str | None) -> float:
    """Similarity in [0, 1] over canonical terms.

    Exact-after-canonicalization -> 1.0. Otherwise the max of a sequence-ratio and
    a sorted-token ratio, so word-order/qualifier variants score high without
    merging genuinely different terms.
    """
    ca, cb = canonical_term(a), canonical_term(b)
    if not ca and not cb:
        return 1.0
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    seq = difflib.SequenceMatcher(None, ca, cb).ratio()
    tok = difflib.SequenceMatcher(
        None, " ".join(sorted(ca.split())), " ".join(sorted(cb.split()))
    ).ratio()
    return max(seq, tok)


def fuzzy_match(a: str | None, b: str | None, threshold: float = FUZZY_MATCH) -> bool:
    """True when the two terms match at or above ``threshold`` (default 0.90)."""
    return similarity(a, b) >= threshold


# --------------------------------------------------------------------------- #
# Agency attribute equivalence (RegulatoryEvent.agency is a scored attribute)
# --------------------------------------------------------------------------- #
# Decision (docs/HANDOFF.md): PMDA and MHLW fold to a MATCH — both are the Japanese
# regulatory jurisdiction (PMDA reviews, MHLW grants); the source rarely distinguishes
# them and the difference is not CI-relevant. All other agencies are distinct, so a
# declined/"other" agency still scores as an attribute error. Agency never blocks a
# match (it was demoted from the key); this only scores attribute accuracy.
_AGENCY_CLASS = {"PMDA": "JP", "MHLW": "JP"}


def agency_class(agency: str | None) -> str | None:
    """Equivalence class for agency attribute scoring (PMDA/MHLW -> 'JP')."""
    return _AGENCY_CLASS.get(agency, agency) if agency is not None else None


def agency_attribute_matches(predicted: str | None, golden: str | None) -> bool:
    """True when two agencies are equivalent for attribute scoring (PMDA==MHLW)."""
    return agency_class(predicted) == agency_class(golden)


# --------------------------------------------------------------------------- #
# Value-scale normalization (MarketMetric.value attribute scoring)
# --------------------------------------------------------------------------- #
_SCALES: dict[str, float] = {
    "trillion": 1e12,
    "billion": 1e9, "bn": 1e9,
    "million": 1e6, "millions": 1e6, "mn": 1e6,
    "thousand": 1e3, "k": 1e3,
}

_METRIC_DIMENSION = {
    "revenue": "currency",
    "growth_rate": "percent",
    "market_share": "percent",
    "patient_count": "count",
    "country_count": "count",
}


def metric_dimension(metric: str) -> str:
    """The comparison dimension implied by a MarketMetric.metric enum value."""
    return _METRIC_DIMENSION.get(metric, "currency")


def unit_scale(unit: str | None) -> float:
    """Scale multiplier parsed from a unit string ('USD billion' -> 1e9)."""
    if not unit:
        return 1.0
    for tok in normalize_text(unit).split():
        if tok in _SCALES:
            return _SCALES[tok]
    return 1.0


def to_base(value: float, unit: str | None) -> float:
    """Value in base units (absolute amount / raw percent / raw count)."""
    return value * unit_scale(unit)


def values_match(
    value_a: float, unit_a: str | None,
    value_b: float, unit_b: str | None,
    *, rel_tol: float = 0.02, abs_eps: float = 1e-9,
) -> bool:
    """Scale-normalized value comparison within ``rel_tol`` (default 2%).

    Absorbs source rounding ('USD 1.3 billion' vs golden 1305 million). The caller
    is responsible for dimension-gating (only compare like metrics); this compares
    magnitudes after ``to_base``.
    """
    a, b = to_base(value_a, unit_a), to_base(value_b, unit_b)
    if abs(a) <= abs_eps and abs(b) <= abs_eps:
        return True
    return abs(a - b) <= rel_tol * max(abs(a), abs(b))
