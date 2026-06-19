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
    # abbreviation <-> spelled-out expansions. The KEY is the multi-word spelled-out form so the phrase
    # loop below applies it IN-STRING (the same mechanism as "iga nephropathy"); a single-token key with
    # a multi-word value is NOT expanded in-string by the single-token step, so the expansion must be the
    # key. A spelled-out form folds to its abbreviation, so an agent's expansion and the golden's
    # abbreviation canonicalize alike (Q2 "AATD", Q8 "NMEs").
    "alpha 1 antitrypsin deficiency": "aatd",
    "new molecular entities": "nmes",
    "new molecular entity": "nme",
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


def _token_set_ratio(ca: str, cb: str) -> float:
    """A TRUE token-SET ratio (fuzzywuzzy/rapidfuzz ``token_set_ratio`` algorithm, on stdlib difflib).

    Compares token SETS, not their char-joined order: it forms the sorted intersection ``t0`` and the
    intersection extended by each side's leftover tokens (``t1``, ``t2``), and returns the max pairwise
    ratio. The load-bearing property: when one term's tokens are a SUBSET of the other's — a reorder
    plus extra words — the smaller side's leftover is empty, so ``t0 == t_subset`` and the ratio is
    **1.0**. This credits "net sales for Q1 2026" vs "Q1 2026 net sales" (subset + one function word)
    WITHOUT enumerating a stopword list. A genuinely different term (no shared tokens) yields an empty
    intersection -> 0.0, so distinct subjects/attributes still fail.
    """
    sa, sb = set(ca.split()), set(cb.split())
    inter = sorted(sa & sb)
    if not inter:                       # no shared tokens -> genuinely different (never spuriously 1.0)
        return 0.0
    diff_a, diff_b = sorted(sa - sb), sorted(sb - sa)
    t0 = " ".join(inter)
    t1 = " ".join(inter + diff_a)
    t2 = " ".join(inter + diff_b)
    r = lambda x, y: difflib.SequenceMatcher(None, x, y).ratio()
    return max(r(t0, t1), r(t0, t2), r(t1, t2))


def similarity(a: str | None, b: str | None) -> float:
    """Similarity in [0, 1] over canonical terms.

    Exact-after-canonicalization -> 1.0. Otherwise the max of a sequence-ratio and
    a sorted-token ratio, so word-order/qualifier variants score high without
    merging genuinely different terms.

    NOTE: this is the **strict** matcher used for extraction/indication matching, where
    subset-containment must NOT match (a narrowing qualifier like "acquired vWD" ⊆ "vWD", or a verbose
    qualifier, is intentionally NOT a true positive — see ``matching._indication_subset``). For AGENT
    (subject, attribute) matching, which must credit a reorder-plus-function-word paraphrase, use
    :func:`token_set_similarity` instead.
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
    """True when the two terms match at or above ``threshold`` (default 0.90), STRICT matcher."""
    return similarity(a, b) >= threshold


def token_set_similarity(a: str | None, b: str | None) -> float:
    """:func:`similarity` augmented with a TRUE token-SET ratio (:func:`_token_set_ratio`).

    Identical to ``similarity`` except a reorder-plus-extra-tokens variant scores ~1.0 (when one token
    set is a subset of the other). ``max`` makes it monotonically >= ``similarity``, so exact matches
    stay 1.0 and nothing regresses. **Scoped to AGENT (subject, attribute) matching** — NOT used for
    extraction indication matching, where subset-containment must stay a non-match. The token-set ratio
    cannot distinguish a benign function word ("for") from a meaning-changing qualifier ("acquired")
    structurally, so applying it only where attribute paraphrase is desired (and where a second value
    gate follows) is deliberate.
    """
    ca, cb = canonical_term(a), canonical_term(b)
    if not ca or not cb:
        return similarity(a, b)
    return max(similarity(a, b), _token_set_ratio(ca, cb))


def token_set_match(a: str | None, b: str | None, threshold: float = FUZZY_MATCH) -> bool:
    """True when the token-SET similarity is at or above ``threshold`` (default 0.90)."""
    return token_set_similarity(a, b) >= threshold


# --------------------------------------------------------------------------- #
# Company self-reference (MarketMetric.subject normalization)
# --------------------------------------------------------------------------- #
# An income statement does not repeat the company name per line, so Flash-Lite
# labels the company's own consolidated figures with a generic subject ("Company").
# Fold those to the document's source_company before comparing MarketMetric.subject
# (the company-level analog of period -> reporting_period). EXACT canonical match
# only, and deliberately EXCLUDING "Total": "Total" is an aggregation marker that
# can denote a segment/summed subject, not the company — folding it would risk the
# weak-alias-chaining failure class seen in the asset over-merge. (Confirmed against
# the artifact: "Total" never appears as a subject; product groups like
# "Sandostatin Group" do, and must NOT fold.)
def fold_self_reference(subject: str | None, source_company: str) -> str | None:
    """Map a generic company self-reference subject to ``source_company`` (exact match)."""
    if not subject:
        return subject
    self_refs = {
        "company",
        "the company",
        "the group",
        canonical_term(source_company),
        canonical_term(f"{source_company} group"),
    }
    return source_company if canonical_term(subject) in self_refs else subject


# Null-sentinel values an extractor emits when it declines to fill an open-text field.
# A predicted fact whose OPEN-TEXT KEY field is one of these can't be cleanly keyed -> it is
# "key-incomplete" (under-specified), scored apart from a clean false positive (see
# matching.is_key_incomplete / docs/LEARNINGS.md). Closed enums have no null sentinel.
_NULL_SENTINELS = {
    "", "not specified", "unspecified", "not stated", "not disclosed", "undisclosed",
    "n a", "na", "none", "unknown", "tbd", "not applicable",
}


def is_null_sentinel(value: str | None) -> bool:
    """True if ``value`` is missing or a decline-to-fill sentinel (e.g. 'not specified')."""
    return value is None or canonical_term(value) in _NULL_SENTINELS


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
