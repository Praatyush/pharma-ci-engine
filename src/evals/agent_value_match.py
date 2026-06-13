"""Deterministic value-matching layer for the Phase 4A agent scorer (Batch 2).

Resolves the Batch-2 gate: ``normalize.py``'s fuzzy path (0.90 threshold) cannot match the
golden's prose values, and mis-handles signed percentages (sign-loss) and the currency ``m``
scale. This layer handles ONLY the finite value shapes present in the 21 committed reference
claims (``src/evals/golden/agent.golden.json``) — **NO fuzzy threshold, NO LLM, NO general
prose matcher.**

Two mechanisms:

- **CLOSED-SET CANONICALIZER** — phase / status[``approved``, ``pending_filing``] / count /
  ``indication_present``: explicit enumerated phrasings -> a canonical atom; two values match
  iff they canonicalize to the same atom.
- **STRUCTURED NUMERIC COMPARATOR** — currency-magnitude (``m`` -> million, **exact** magnitude;
  fixes gate defect 2) and signed-percentage-pair (**sign-PRESERVED**, component-wise; fixes gate
  defect 1).

**DISPATCH** routes a value by recognizable structure (``%`` -> percent-pair; a currency token or
number+scale -> magnitude; else a closed-set atom). A value matching **NO** known shape **RAISES**
:class:`UnrecognizedValueShape` — never a silent default.

Ratifications applied (human-decided against source; see the Batch-2 thread + ``docs/AGENT_CONTRACT.md``):

- **Reading 1** — for compound values only the value ATOM matches; the year/region/detail are
  carried by the attribute/question/span and do NOT participate.
- **STOP A** — ``filed`` and ``under regulatory submission`` collapse to ONE ``pending_filing`` atom
  (Takeda's "Filed (date)" and Novartis's "submission / priority review" denote the SAME regulatory
  state in two source-doc vocabularies; matching scores the regulatory STATE, not the house-style
  word). ``approved`` stays DISTINCT (decision granted != pending), so "filed" for an approved asset
  scores as wrong-value.
- **STOP B** — Q6-c2 -> an ``indication_present`` atom; the "no separate stage/status/figure stated"
  clause is carried by the attribute, NOT string-matched. A stage-claiming agent answer canonicalizes
  to a PHASE atom and so correctly FAILS to match ``indication_present`` (the coarsest match in the
  set: presence vs. not — intentional).
- **Q3-c3** -> a PHASE atom (the "first planned submission 2027" is a future plan, not a current
  submission status), so PHASE is checked BEFORE the status atoms.

``matching.collapse_phase`` is NOT reused for phase canonicalization: it only strips sub-phase letters
(``P2b -> P2``) and leaves ``Phase III`` / ``P-III`` / ``Phase 3`` / ``P3`` un-folded (verified at
build), so the thin phase canonicalizer below (roman/arabic/format -> phase number) is required.
"""

import re


class UnrecognizedValueShape(ValueError):
    """A value matched none of the finite shapes present in the golden — raised, never defaulted."""


# --------------------------------------------------------------------------- #
# Structured numeric comparator
# --------------------------------------------------------------------------- #
# Scale map — note ``m`` is included (the gate's defect 2: ``normalize._SCALES`` had only ``mn``).
_SCALE = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mn": 1e6, "million": 1e6, "millions": 1e6,
    "bn": 1e9, "billion": 1e9,
    "trillion": 1e12,
}
_CURRENCY_RE = re.compile(r"\b(usd|eur|gbp|jpy|chf)\b|(\$)")
_SCALE_TOKENS = "k|m|mn|bn|million|millions|billion|thousand|trillion"
_HAS_MAGNITUDE_RE = re.compile(rf"\d[\d,]*(?:\.\d+)?\s*(?:{_SCALE_TOKENS})\b")
# Number may use a comma OR a space as a thousands separator; the space form is SCOPED to digit-triplets
# (``\s\d{3}`` -> "1 516" is one number), so a bare space between unrelated numbers is NOT merged.
_AMOUNT_RE = re.compile(rf"(\d[\d,]*(?:\s\d{{3}})*(?:\.\d+)?)\s*({_SCALE_TOKENS})?\b")

_PCT_USD = {"usd", "reported", "dollar", "dollars", "$"}
_PCT_CC = {"cc", "constant", "constant currency", "constant-currency"}
_PCT_RE = re.compile(r"([+-]?)\s*(\d+(?:\.\d+)?)\s*%\s*\(?\s*([a-z]+(?:\s+[a-z]+)?)?")
# Sentinel key for a percentage whose currency component is unresolved (a degenerate/partial percent).
# It can never equal a real "USD"/"cc" component, so a partial value never matches a proper pair.
_PARTIAL_PCT = "__partial_pct__"


def _looks_currency(low: str) -> bool:
    """A currency token, or a number bearing a magnitude scale (so bare '8' is NOT currency)."""
    return bool(_CURRENCY_RE.search(low) or _HAS_MAGNITUDE_RE.search(low))


def _parse_currency(value: str) -> tuple[float, str | None]:
    """``"USD 1,164m"`` -> ``(1.164e9, "usd")``; scale normalized (m->million). Currency optional."""
    low = value.lower()
    cm = _CURRENCY_RE.search(low)
    currency = (cm.group(1) or cm.group(2)) if cm else None
    am = _AMOUNT_RE.search(low)
    if not am:
        raise UnrecognizedValueShape(value)
    magnitude = float(am.group(1).replace(",", "").replace(" ", "")) * (_SCALE.get(am.group(2), 1.0) if am.group(2) else 1.0)
    return magnitude, currency


def _percent_component(label: str | None) -> str | None:
    if not label:
        return None
    l = label.strip().strip("()").strip()
    if l in _PCT_USD:
        return "USD"
    if l in _PCT_CC:
        return "cc"
    head = l.split()[0] if l.split() else ""
    if head in _PCT_USD:
        return "USD"
    if head in _PCT_CC:
        return "cc"
    return None


def _parse_percent_pair(value: str) -> frozenset:
    """``"+2% USD / -2% cc"`` -> ``frozenset({("USD", 2.0), ("cc", -2.0)})`` — SIGN PRESERVED.

    PRINCIPLED LINE (do not turn the raise into a knob): a percent NUMBER whose currency component
    cannot be resolved (e.g. the agent's bare, sign-less ``"2%"`` — missing the cc component and/or the
    sign) is a DEGENERATE/PARTIAL instance of the EXPECTED percentage-pair shape: the agent attempted the
    right KIND of value and gave it incomplete. It is recorded under the ``_PARTIAL_PCT`` sentinel — which
    can never equal a real ``USD``/``cc`` component — so ``value_match`` returns False (a WRONG VALUE /
    recall miss + wrong-value diagnostic), NOT an error. This is an AGENT mistake, not a scorer coverage
    gap. The raise is RESERVED for its real purpose: a ``"%"`` string with NO parseable percentage at all
    is not a percentage the scorer can classify, and still raises loud (and a value matching no known
    shape at all still raises at :func:`classify`).
    """
    out: dict[str, float] = {}
    for i, (sign, num, label) in enumerate(_PCT_RE.findall(value.lower())):
        comp = _percent_component(label)
        key = comp if comp is not None else f"{_PARTIAL_PCT}{i}"   # degenerate percent -> non-matching key
        out[key] = float(num) * (-1.0 if sign == "-" else 1.0)
    if not out:
        raise UnrecognizedValueShape(value)                        # no percentage at all -> still loud
    return frozenset((k, round(v, 6)) for k, v in out.items())


# --------------------------------------------------------------------------- #
# Closed-set canonicalizer
# --------------------------------------------------------------------------- #
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6}
_PHASE_WORD_RE = re.compile(r"\bphase[-\s]+([ivx]+|\d+)\b")
_PHASE_P_HYPHEN_RE = re.compile(r"\bp-(iii|ii|iv|i|v|\d+)\b")   # "P-III" (hyphen required for roman)
_PHASE_P_DIGIT_RE = re.compile(r"\bp(\d+)\b")                   # "P3"  (avoids "PV" -> phase)

# Substring markers (matched on lowercased text). Order in _closed_set_atom is load-bearing.
_INDICATION_PRESENT = ("listed indication", "is an indication for", "an indication for",
                       "indication for", "indicated for", "marketed for", "approved indication for")
_APPROVED = ("approved", "approval")
_PENDING_FILING = ("filed", "filing", "submission", "submitted", "submit", "under review")

_NUMWORD = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_COUNT_UNITS = {"nme", "nmes", "lcm", "lcms", "program", "programs", "asset", "assets",
                "project", "projects", "entity", "entities"}


def _phase_number(low: str) -> int | None:
    """Phase atom -> its integer (``Phase III``/``Phase 3``/``P-III``/``P3`` -> 3); else None.

    "P3"/"P-III" forms are restricted so the abbreviation "PV" (polycythemia vera) does NOT canonicalize
    to a phase (it would otherwise read "P" + "V" = phase 5).
    """
    m = _PHASE_WORD_RE.search(low) or _PHASE_P_HYPHEN_RE.search(low) or _PHASE_P_DIGIT_RE.search(low)
    if not m:
        return None
    g = m.group(1)
    return int(g) if g.isdigit() else _ROMAN.get(g)


def _count_int(low: str) -> int | None:
    """Bare count atom: ``"8"`` / ``"8 NMEs"`` / ``"eight"`` -> 8 (count-unit words stripped); else None."""
    toks = [t for t in re.split(r"[^a-z0-9]+", low) if t and t not in _COUNT_UNITS]
    if len(toks) == 1:
        t = toks[0]
        if t.isdigit():
            return int(t)
        if t in _NUMWORD:
            return _NUMWORD[t]
    return None


def _closed_set_atom(low: str):
    """Return ``(shape, key)`` for a closed-set value, or None. Priority is load-bearing:
    PHASE first (Q3-c3 'Phase III ... submission' is a phase, not pending); indication_present before
    approved (so 'approved indication for' -> presence, not approval status)."""
    ph = _phase_number(low)
    if ph is not None:
        return ("phase", ph)
    if any(s in low for s in _INDICATION_PRESENT):
        return ("indication_present", "indication_present")
    if any(s in low for s in _APPROVED):
        return ("approved", "approved")
    if any(s in low for s in _PENDING_FILING):
        return ("pending_filing", "pending_filing")
    c = _count_int(low)
    if c is not None:
        return ("count", c)
    return None


# --------------------------------------------------------------------------- #
# Dispatch + public API
# --------------------------------------------------------------------------- #
def classify(value: str):
    """Route a value to its shape -> ``(shape, key)``. Raises :class:`UnrecognizedValueShape`
    if it matches none of the finite shapes present in the golden (never a silent default)."""
    v = value.strip()
    low = v.lower()
    if "%" in v:
        return ("percent", _parse_percent_pair(v))
    if _looks_currency(low):
        return ("currency", _parse_currency(v))
    atom = _closed_set_atom(low)
    if atom is not None:
        return atom
    raise UnrecognizedValueShape(value)


def value_match(a: str, b: str) -> bool:
    """True iff two value strings match per the ratified deterministic layer.

    Different shapes never match (e.g. a PHASE answer vs an ``indication_present`` golden, or
    ``approved`` vs ``pending_filing``). Currency compares EXACT normalized magnitude (currency token
    blocks only if both present and differ). Percent compares the sign-preserved component set.
    """
    ca = classify(a)
    cb = classify(b)
    if ca[0] != cb[0]:
        return False
    shape = ca[0]
    if shape == "currency":
        (ma, cura), (mb, curb) = ca[1], cb[1]
        if cura and curb and cura != curb:
            return False
        return abs(ma - mb) <= 1e-6 * max(abs(ma), abs(mb), 1.0)
    # percent (frozenset) and closed-set atoms (token / int) all compare by equality of the key.
    return ca[1] == cb[1]
