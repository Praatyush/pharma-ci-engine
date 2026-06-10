"""Duplicate-collapse + predicted<->golden matching (the approved keys).

Two jobs, both upstream of metrics (which only counts what this module aligns):

1. **Collapse** — per-chunk extraction emits the same fact many times (an asset
   spanning N chunks; a fact straddling chunk overlap). Before any scoring we fold
   duplicates so counts are *type-level* ("did the system find this distinct fact
   at all"). Assets collapse by **shared-identifier union-find** (the same molecule
   is referenced as ``ianalumab`` and ``VAY736``); facts collapse by their match key.

2. **Match** — align collapsed predictions to golden labels using the approved
   per-type keys (closed enums exact; open fields fuzzy via ``normalize``; assets by
   identifier-cluster overlap). Produces (matched, false-positives, misses); turning
   those into precision/recall/F1 is ``metrics.py`` (not built yet).

Approved keys (docs/HANDOFF.md):
  Program          (asset, indication~, region, stage)
  Trial            nct_id -> trial_name~ -> (assets + indication~ + phase)
  RegulatoryEvent  (asset, action, indication~, region)        agency = attribute
  MarketMetric     (subject~, metric, geography~)              period/value = attributes
"""

import re
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .normalize import canonical_term, fuzzy_match, is_null_sentinel, slug

_SUBPHASE_RE = re.compile(r"^(P?\d)[ab]$")


def collapse_phase(value: str) -> str:
    """Collapse a sub-phase to its parent for KEY purposes: P2a/P2b->P2, 2a/2b->2.

    A sub-distinction the source makes but the key shouldn't gate on (the stage analog of the
    agency PMDA==MHLW fold). Golden keeps the precise sub-phase; the key uses the collapsed one.
    Leaves P1/2, 1/2, preclinical, filed, approved, etc. unchanged.
    """
    return _SUBPHASE_RE.sub(r"\1", value)


# --------------------------------------------------------------------------- #
# Asset identifier-cluster index (union-find)
# --------------------------------------------------------------------------- #
class _DSU:
    """Tiny union-find over identifier slugs."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


@dataclass(frozen=True)
class _Cluster:
    canonical: str
    slugs: frozenset[str]
    size: int  # number of raw assets that fell into this cluster


@dataclass
class AssetIndex:
    """Resolves an asset slug to its molecule's canonical slug + full slug set."""

    _canonical: dict[str, str]
    _slugs: dict[str, frozenset[str]]
    clusters: list[_Cluster]

    @property
    def num_clusters(self) -> int:
        return len(self.clusters)

    def resolve(self, raw_slug: str) -> str:
        """Canonical slug for a raw slug (the slug itself if unseen / dangling)."""
        return self._canonical.get(raw_slug, raw_slug)

    def cluster_slugs(self, raw_slug: str) -> frozenset[str]:
        """All identifier slugs of the molecule a slug belongs to."""
        return self._slugs.get(self.resolve(raw_slug), frozenset({raw_slug}))


def _build_index(id_groups: list[list[str]]) -> AssetIndex:
    """Build an :class:`AssetIndex` from one identifier-string list per asset."""
    dsu = _DSU()
    group_slugs: list[frozenset[str]] = []
    for identifiers in id_groups:
        slugs = {slug(s) for s in identifiers if s and s.strip()}
        slugs.discard("unknown")
        group_slugs.append(frozenset(slugs))
        slist = list(slugs)
        for other in slist[1:]:
            dsu.union(slist[0], other)

    root_slugs: dict[str, set[str]] = {}
    root_size: dict[str, int] = {}
    for slugs in group_slugs:
        if not slugs:
            continue
        root = dsu.find(next(iter(slugs)))
        root_slugs.setdefault(root, set()).update(slugs)
        root_size[root] = root_size.get(root, 0) + 1

    canonical: dict[str, str] = {}
    cluster_slugs: dict[str, frozenset[str]] = {}
    clusters: list[_Cluster] = []
    for root, slugs in root_slugs.items():
        canon = min(slugs)  # deterministic representative
        frozen = frozenset(slugs)
        for s in slugs:
            canonical[s] = canon
        cluster_slugs[canon] = frozen
        clusters.append(_Cluster(canon, frozen, root_size[root]))
    clusters.sort(key=lambda c: c.canonical)
    return AssetIndex(canonical, cluster_slugs, clusters)


def build_asset_index(assets: Iterable[Any]) -> AssetIndex:
    """From predicted ``schema.Asset`` objects (id + all human identifier fields)."""
    groups = [
        [a.id, a.generic_name, *a.development_codes, *a.brand_names, *a.aliases]
        for a in assets
    ]
    return _build_index([[s for s in g if s] for g in groups])


def build_golden_asset_index(golden_assets: Iterable[Any]) -> AssetIndex:
    """From ``labels.GoldenAsset`` objects (their ``identifiers`` lists)."""
    return _build_index([list(a.identifiers) for a in golden_assets])


# --------------------------------------------------------------------------- #
# Per-type collapse keys (hashable; open fields normalized-exact)
# --------------------------------------------------------------------------- #
def program_key(p: Any, idx: AssetIndex) -> Hashable:
    return (idx.resolve(p.asset_id), canonical_term(p.indication), p.region, collapse_phase(p.stage))


def trial_key(t: Any, idx: AssetIndex) -> Hashable:
    if t.nct_id:
        return ("nct", t.nct_id.strip().lower())
    if t.trial_name:
        return ("name", canonical_term(t.trial_name))
    return (
        "triple",
        frozenset(idx.resolve(a) for a in t.asset_ids),
        canonical_term(t.indication),
        collapse_phase(t.phase),
    )


def regevent_key(r: Any, idx: AssetIndex) -> Hashable:
    return (idx.resolve(r.asset_id), r.action, canonical_term(r.indication), r.region)


def metric_key(m: Any, idx: AssetIndex | None = None) -> Hashable:
    return (canonical_term(m.subject), m.metric, canonical_term(m.geography))


# --------------------------------------------------------------------------- #
# Collapse
# --------------------------------------------------------------------------- #
def _collapse_by_key(items: list[Any], key_of: Callable[[Any], Hashable]) -> list[Any]:
    """Keep the first item per key (document order); fold the rest away."""
    seen: dict[Hashable, Any] = {}
    for item in items:
        k = key_of(item)
        if k not in seen:
            seen[k] = item
    return list(seen.values())


@dataclass
class CollapsedResult:
    """Deduplicated entities + raw/collapsed counts per type."""

    asset_index: AssetIndex
    programs: list[Any]
    trials: list[Any]
    regulatory_events: list[Any]
    market_metrics: list[Any]
    raw_counts: dict[str, int] = field(default_factory=dict)

    @property
    def collapsed_counts(self) -> dict[str, int]:
        return {
            "assets": self.asset_index.num_clusters,
            "programs": len(self.programs),
            "trials": len(self.trials),
            "regulatory_events": len(self.regulatory_events),
            "market_metrics": len(self.market_metrics),
        }

    def summary(self) -> dict[str, tuple[int, int]]:
        """{type: (raw, collapsed)} for reporting dedup effect."""
        collapsed = self.collapsed_counts
        return {k: (self.raw_counts.get(k, 0), collapsed[k]) for k in collapsed}


def collapse(result: Any) -> CollapsedResult:
    """Collapse an ``extraction.ExtractionResult`` to type-level distinct entities."""
    idx = build_asset_index(result.assets)
    return CollapsedResult(
        asset_index=idx,
        programs=_collapse_by_key(result.programs, lambda p: program_key(p, idx)),
        trials=_collapse_by_key(result.trials, lambda t: trial_key(t, idx)),
        regulatory_events=_collapse_by_key(result.regulatory_events, lambda r: regevent_key(r, idx)),
        market_metrics=_collapse_by_key(result.market_metrics, lambda m: metric_key(m, idx)),
        raw_counts={
            "assets": len(result.assets),
            "programs": len(result.programs),
            "trials": len(result.trials),
            "regulatory_events": len(result.regulatory_events),
            "market_metrics": len(result.market_metrics),
        },
    )


# --------------------------------------------------------------------------- #
# Predicted <-> golden match predicates (closed exact; open fuzzy; asset overlap)
# --------------------------------------------------------------------------- #
def _assets_overlap(pred_slugs: frozenset[str], gold_slugs: frozenset[str]) -> bool:
    return bool(pred_slugs & gold_slugs)


def program_matches(p: Any, g: Any, pidx: AssetIndex, gidx: AssetIndex) -> bool:
    return (
        _assets_overlap(pidx.cluster_slugs(p.asset_id), gidx.cluster_slugs(slug(g.asset)))
        and (g.region is None or p.region == g.region)  # null golden region = indeterminate
        and collapse_phase(p.stage) == collapse_phase(g.stage)
        and fuzzy_match(p.indication, g.indication)
    )


def regevent_matches(r: Any, g: Any, pidx: AssetIndex, gidx: AssetIndex) -> bool:
    return (
        _assets_overlap(pidx.cluster_slugs(r.asset_id), gidx.cluster_slugs(slug(g.asset)))
        and r.action == g.action
        and r.region == g.region
        and fuzzy_match(r.indication, g.indication)
    )


def trial_matches(t: Any, g: Any, pidx: AssetIndex, gidx: AssetIndex) -> bool:
    if t.nct_id and g.nct_id:
        return t.nct_id.strip().lower() == g.nct_id.strip().lower()
    if t.trial_name and g.trial_name:
        return fuzzy_match(t.trial_name, g.trial_name)
    pred_slugs = frozenset().union(*(pidx.cluster_slugs(a) for a in t.asset_ids)) if t.asset_ids else frozenset()
    gold_slugs = frozenset().union(*(gidx.cluster_slugs(slug(a)) for a in g.assets)) if g.assets else frozenset()
    return (
        _assets_overlap(pred_slugs, gold_slugs)
        and collapse_phase(t.phase) == collapse_phase(g.phase)
        and fuzzy_match(t.indication, g.indication)
    )


def metric_matches(m: Any, g: Any, pidx: AssetIndex, gidx: AssetIndex) -> bool:
    return (
        m.metric == g.metric
        and fuzzy_match(m.subject, g.subject)
        and fuzzy_match(m.geography, g.geography)
    )


_PREDICATES: dict[str, Callable[[Any, Any, AssetIndex, AssetIndex], bool]] = {
    "programs": program_matches,
    "trials": trial_matches,
    "regulatory_events": regevent_matches,
    "market_metrics": metric_matches,
}


# Open-text key fields per type — a null sentinel here means the entity can't be cleanly
# keyed (under-specified), so it is "key-incomplete" rather than a clean false positive.
# Trials are exempt while they carry an nct_id or trial_name (those key them instead).
_OPEN_KEY_FIELDS: dict[str, Callable[[Any], list[Any]]] = {
    "programs": lambda p: [p.indication],
    "regulatory_events": lambda r: [r.indication],
    "trials": lambda t: [] if (t.nct_id or t.trial_name) else [t.indication],
    "market_metrics": lambda m: [m.subject, m.geography],
}


def is_key_incomplete(entity: Any, entity_type: str) -> bool:
    """True if a predicted entity has a null-sentinel in an open-text key field.

    Such an entity (e.g. a regulatory designation with ``indication='not specified'``) is
    under-specified, not hallucinated — it is scored apart from a clean false positive so
    precision doesn't charge a phantom FP for under-specification (see docs/LEARNINGS.md).
    """
    getter = _OPEN_KEY_FIELDS.get(entity_type)
    return bool(getter) and any(is_null_sentinel(v) for v in getter(entity))


@dataclass
class MatchOutcome:
    """Alignment of collapsed predictions to golden labels for one entity type."""

    matched: list[tuple[Any, Any]]  # (predicted, golden)
    false_positives: list[Any]      # predicted with no golden match (a clean, keyable fact)
    misses: list[Any]               # golden with no predicted match
    key_incomplete: list[Any] = field(default_factory=list)  # predicted, unmatched, null-sentinel key


def match_lists(
    predicted: list[Any],
    golden: list[Any],
    entity_type: str,
    pidx: AssetIndex,
    gidx: AssetIndex,
) -> MatchOutcome:
    """Greedily align predictions to golden via the per-type key predicate.

    One-to-one: each golden label claims at most one predicted entity. Unmatched golden
    labels are misses. Unmatched predictions split into ``key_incomplete`` (a null-sentinel
    in an open-text key field — under-specified) and ``false_positives`` (clean, keyable but
    unmatched). (Counting these into precision/recall/F1 is metrics.py.)
    """
    predicate = _PREDICATES[entity_type]
    used: set[int] = set()
    matched: list[tuple[Any, Any]] = []
    for g in golden:
        for i, p in enumerate(predicted):
            if i in used:
                continue
            if predicate(p, g, pidx, gidx):
                matched.append((p, g))
                used.add(i)
                break
    unmatched = [p for i, p in enumerate(predicted) if i not in used]
    key_incomplete = [p for p in unmatched if is_key_incomplete(p, entity_type)]
    false_positives = [p for p in unmatched if not is_key_incomplete(p, entity_type)]
    matched_golden = {id(g) for _, g in matched}
    misses = [g for g in golden if id(g) not in matched_golden]
    return MatchOutcome(matched, false_positives, misses, key_incomplete)
