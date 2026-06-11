"""Grounding check: does a PREDICTED fact's cited ``line_range`` actually contain it?

Predicted-fact-vs-source-text — no golden labels — so it runs against the full extraction
artifacts independently of labeling. For each fact, read the **load-bearing**
``source_ref.line_range`` and check whether the fact's salient tokens are present, using a
surface-form map for closed enums (source writes "Approved"/"PhIII"/"Japan"; the schema stores
``approval``/``3``/``JP`` — the reverse of ``normalize.canonical_term``).

Each token is categorized, because a missing token has distinct causes that must not be
conflated (see docs/LEARNINGS.md):

- ``grounded``      — surface present in the cited lines.
- ``real_failure``  — genuinely absent: wrong line cited / fact not in the text (a provenance
                      fault).
- ``map_gap``       — a recognizable surface IS present but the synonym map deliberately/
                      incompletely doesn't bridge it (e.g. bare "3" for phase, ambiguous with
                      years) — a fixable token-map gap, NOT an extraction fault.
- ``inferred``      — (region) no region word is in the text at all; the model asserted a
                      region the source never states (the predicted-side mirror of golden
                      policy 3). Reported as its own prominent number.
- ``indeterminate`` — partial evidence (some indication tokens present, below threshold) —
                      ambiguous between paraphrase and wrong-line.

``line_range`` is the containment check; ``snippet`` is decorative — on mashed table rows the
extractor falls back to chunk text (``snippet_fallback``), which is EXPECTED, not a failure.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .normalize import canonical_term, slug

# Schema enum value -> source surface forms (lowercased): the reverse of canonical_term.
_ENUM_SURFACES: dict[str, list[str]] = {
    # RegulatoryAction
    "approval": ["approved", "approval"],
    "filed": ["filed", "filing", "submission", "submitted", "submissions"],
    "CRL": ["crl", "complete response letter"],
    "priority_review": ["priority review"],
    "breakthrough": ["breakthrough"],
    "fast_track": ["fast track"],
    "orphan": ["orphan"],
    "PRIME": ["prime", "priority medicines"],
    "CHMP_opinion": ["chmp"],
    "application_withdrawal": ["withdrew", "withdrawal", "withdrawn"],
    "product_withdrawal": ["withdrawn", "withdrawal"],
    # ProgramStage
    "preclinical": ["preclinical", "pre-clinical"],
    "approved": ["approved", "approval"],
    "discontinued": ["discontinued", "terminated"],
    "P1": ["p-i", "phase 1", "ph 1", "ph1", "phase i"],
    "P1/2": ["p-i/ii", "phase 1/2", "phi/ii", "ph 1/2"],
    "P2": ["p-ii", "phase 2", "ph 2", "ph2", "phase ii"],
    "P2a": ["phase 2a", "p-iia"],
    "P2b": ["phase 2b", "p-iib"],
    "P3": ["p-iii", "phase 3", "ph 3", "ph3", "phase iii"],
    # TrialPhase
    "1": ["phase 1", "ph 1", "p-i", "phi"],
    "1/2": ["phase 1/2", "phi/ii", "ph i/ii", "p-i/ii"],
    "2": ["phase 2", "ph 2", "p-ii", "phii"],
    "2a": ["phase 2a", "p-iia"],
    "2b": ["phase 2b", "p-iib"],
    "3": ["phase 3", "ph 3", "p-iii", "phiii"],
    "4": ["phase 4", "ph 4", "p-iv"],
    # Region
    "US": ["us", "u.s.", "united states", "fda"],
    "EU": ["eu", "europe", "european", "ema", "chmp"],
    "JP": ["japan", "jp", "pmda", "mhlw"],
    "CN": ["china", "cn", "nmpa"],
    "Global": ["global", "worldwide"],
    "other": [],
}
_REGION_SURFACES = [s for v in ("US", "EU", "JP", "CN", "Global") for s in _ENUM_SURFACES[v]]


def _cited_text(source_lines: list[str], line_range: tuple[int, int]) -> str:
    a, b = line_range
    return "\n".join(source_lines[a - 1:b])


def _contains(text_low: str, surface: str) -> bool:
    """Token-boundary match — so 'us' grounds 'US' but not 'lupus'/'erythematosus'."""
    return re.search(rf"(?<![a-z0-9]){re.escape(surface)}(?![a-z0-9])", text_low) is not None


def _has_surface(text_low: str, value: str) -> bool:
    surfaces = _ENUM_SURFACES.get(value, [value.lower()]) or [value.lower()]
    return any(_contains(text_low, s) for s in surfaces)


def _asset_grounded(asset_slug: str, cited: str) -> bool:
    return bool(asset_slug) and asset_slug in slug(cited)


def _indication_hits(indication: str | None, cited: str) -> tuple[int, int]:
    toks = [t for t in canonical_term(indication).split() if len(t) > 2]
    cited_can = canonical_term(cited)
    return sum(t in cited_can for t in toks), len(toks)


def _value_grounded(value: float, text_low: str) -> bool:
    compact = re.sub(r"[\s,]", "", text_low)
    forms = {f"{value:g}", str(value)}
    if float(value).is_integer():
        forms.add(str(int(value)))
    return any(f in text_low or f in compact for f in forms)


@dataclass
class TokenCheck:
    name: str
    expected: str
    found: bool
    category: str  # grounded | real_failure | map_gap | inferred | indeterminate


@dataclass
class GroundingResult:
    entity_type: str
    summary: str
    line_range: tuple[int, int]
    checks: list[TokenCheck] = field(default_factory=list)
    snippet_fallback: bool = False


def _categorize(name: str, value: str, found: bool, low: str, cited: str) -> str:
    if found:
        return "grounded"
    if name in ("stage", "phase"):
        digit = value if name == "phase" else value.lstrip("P")
        # bare digit present but unmapped (e.g. Novartis "... 2028 3") -> map gap, not a fault
        if re.search(rf"(?<!\d){re.escape(digit)}(?!\d)", low):
            return "map_gap"
        return "real_failure"
    if name == "region":
        # no region word at all -> the model inferred a region the source never states
        return "real_failure" if any(_contains(low, s) for s in _REGION_SURFACES) else "inferred"
    if name == "indication":
        hits, _ = _indication_hits(value, cited)
        return "indeterminate" if hits > 0 else "real_failure"
    return "real_failure"  # asset, action, subject, value: present-or-not, no map ambiguity


def _summary(t: str, f: Any) -> str:
    if t == "programs":
        return f"{f.asset_id} | {f.indication} | {f.region}/{f.stage}"
    if t == "regulatory_events":
        return f"{f.asset_id} | {f.action} | {f.region} | {f.indication}"
    if t == "trials":
        return f"{f.trial_name} | {f.asset_ids} | P{f.phase} | {f.indication}"
    return f"{f.subject} | {f.metric} | {f.value} {f.unit}"


def ground_fact(fact: Any, entity_type: str, source_lines: list[str]) -> GroundingResult:
    """Ground one predicted fact against its cited line_range; categorize every token."""
    lr = tuple(fact.source_ref.line_range)
    cited = _cited_text(source_lines, lr)
    low = cited.lower()
    checks: list[TokenCheck] = []

    def add(name: str, value: str | None, found: bool) -> None:
        checks.append(TokenCheck(name, str(value), found, _categorize(name, str(value), found, low, cited)))

    if entity_type == "programs":
        add("asset", fact.asset_id, _asset_grounded(fact.asset_id, cited))
        add("stage", fact.stage, _has_surface(low, fact.stage))
        add("region", fact.region, _has_surface(low, fact.region))
        h, n = _indication_hits(fact.indication, cited)
        add("indication", fact.indication, n == 0 or h / n >= 0.5)
    elif entity_type == "regulatory_events":
        add("asset", fact.asset_id, _asset_grounded(fact.asset_id, cited))
        add("action", fact.action, _has_surface(low, fact.action))
        add("region", fact.region, _has_surface(low, fact.region))
        h, n = _indication_hits(fact.indication, cited)
        add("indication", fact.indication, n == 0 or h / n >= 0.5)
    elif entity_type == "trials":
        if fact.trial_name:
            add("asset", fact.trial_name, fact.trial_name.lower() in low)
        else:
            aid = fact.asset_ids[0] if fact.asset_ids else ""
            add("asset", aid, _asset_grounded(aid, cited))
        add("phase", fact.phase, _has_surface(low, fact.phase))
        h, n = _indication_hits(fact.indication, cited)
        add("indication", fact.indication, n == 0 or h / n >= 0.5)
    elif entity_type == "market_metrics":
        subj_toks = [t for t in canonical_term(fact.subject).split() if len(t) > 2]
        add("asset", fact.subject, any(t in low for t in subj_toks))
        add("value", str(fact.value), _value_grounded(fact.value, low))

    snippet = fact.source_ref.snippet or ""
    fallback = len(snippet) >= 200 or "\n" in snippet.strip()
    return GroundingResult(entity_type, _summary(entity_type, fact), lr, checks, fallback)


def aggregate(results: list[GroundingResult]) -> dict[str, Any]:
    """Per-token-name category counts + snippet-fallback rate across many results."""
    by_token: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    fallback = 0
    for r in results:
        fallback += r.snippet_fallback
        for c in r.checks:
            by_token[c.name][c.category] += 1
    return {"by_token": {k: dict(v) for k, v in by_token.items()},
            "snippet_fallback": (fallback, len(results))}
