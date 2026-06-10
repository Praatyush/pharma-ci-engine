"""Extraction-accuracy scoring over the golden set -> a hand-inspectable report.

Pinned design (docs/HANDOFF.md, docs/LEARNINGS.md 2026-06-10):

- **Scope before collapse, over the union.** Scope raw predictions to the UNION of a
  document's labeled chunk line-ranges, collapse ONCE within that union, and match the
  union of golden labels (golden is collapsed too, so a fact labeled in two chunks counts
  once). Never collapse-then-scope; never sum per-chunk (double-counts).
- **Per-type P/R/F1**, with ``key_incomplete`` (under-specified predictions, see
  ``matching``) counted apart from clean false positives — precision does not eat a phantom
  FP for under-specification.
- **Reg-events at two grains:** standalone (``from_progress_row=false``) vs progress-row,
  AND region-split vs region-collapsed (so one 4-region sentence can't dominate recall).
- **Asset recall** over labeled chunks is reported; **asset precision is document-level**
  and withheld unless the full document is labeled (assets carry no ``source_ref``). The
  over-merge (distinct molecules sharing one predicted cluster) is reported as a diagnostic.
- **Inspectable lists.** Every miss / false-positive / key-incomplete / attribute-error item
  carries the source ``line_range`` + a snippet, so a recall number is defensible by hand.

This module does NOT declare a baseline or build grounding/judge/runner — it scores and
renders. The CLI wiring is a later step.
"""

from dataclasses import dataclass, field
from typing import Any

from .labels import GoldenDocument
from .matching import (
    AssetIndex,
    _collapse_by_key,
    build_asset_index,
    build_golden_asset_index,
    collapse_phase,
    is_key_incomplete,
    match_lists,
    metric_key,
    program_key,
    regevent_key,
    trial_key,
)
from .normalize import (
    agency_attribute_matches,
    canonical_term,
    fold_self_reference,
    fuzzy_match,
    is_null_sentinel,
    slug,
    values_match,
)

_FACT_TYPES = ("programs", "trials", "regulatory_events", "market_metrics")


# --------------------------------------------------------------------------- #
# Golden-side collapse keys (mirror the predicted keys in matching, on Golden* fields)
# --------------------------------------------------------------------------- #
def _g_program_key(g: Any, idx: AssetIndex) -> Any:
    return (idx.resolve(slug(g.asset)), canonical_term(g.indication), g.region, collapse_phase(g.stage))


def _g_regevent_key(g: Any, idx: AssetIndex) -> Any:
    return (idx.resolve(slug(g.asset)), g.action, canonical_term(g.indication), g.region)


def _g_trial_key(g: Any, idx: AssetIndex) -> Any:
    if g.nct_id:
        return ("nct", g.nct_id.strip().lower())
    if g.trial_name:
        return ("name", canonical_term(g.trial_name))
    return ("triple", frozenset(idx.resolve(slug(a)) for a in g.assets),
            canonical_term(g.indication), collapse_phase(g.phase))


def _g_metric_key(g: Any, idx: AssetIndex | None = None) -> Any:
    return (canonical_term(g.subject), g.metric, canonical_term(g.geography))


_PRED_KEYS = {"programs": program_key, "trials": trial_key,
              "regulatory_events": regevent_key, "market_metrics": metric_key}
_GOLD_KEYS = {"programs": _g_program_key, "trials": _g_trial_key,
              "regulatory_events": _g_regevent_key, "market_metrics": _g_metric_key}


# --------------------------------------------------------------------------- #
# Provenance helpers
# --------------------------------------------------------------------------- #
def _locate(source_lines: list[str], line_range: tuple[int, int], keywords: list[str]) -> tuple[int, str]:
    """Locate the source line for a fact by keyword *priority* (asset first, then weaker).

    Returns ``(line_no, text)`` of the first line matching the highest-priority keyword
    found within ``line_range``; falls back to the range's first line.
    """
    a, b = line_range
    hi = min(b, len(source_lines))
    for kw in keywords:
        if not kw:
            continue
        for i in range(a, hi + 1):
            if kw.lower() in source_lines[i - 1].lower():
                return i, source_lines[i - 1].strip()
    return a, (source_lines[a - 1].strip() if 0 < a <= len(source_lines) else "")


def _g_keywords(t: str, g: Any) -> list[str]:
    asset = getattr(g, "asset", None) or (g.assets[0] if getattr(g, "assets", None) else None)
    subj = getattr(g, "subject", None)
    ind = (getattr(g, "indication", "") or "").split()
    return [k for k in [asset, subj, getattr(g, "trial_name", None), ind[0] if ind else None] if k]


def _summary(t: str, o: Any, golden: bool) -> str:
    a = getattr(o, "asset", None) if golden else getattr(o, "asset_id", None)
    if t == "programs":
        return f"{a} | {o.indication} | {o.region}/{o.stage}"
    if t == "regulatory_events":
        return f"{a} | {o.action} | {o.region} | {o.indication} | agency={o.agency}"
    if t == "trials":
        assets = getattr(o, "assets", None) or getattr(o, "asset_ids", [])
        return f"{o.trial_name} | {list(assets)} | P{o.phase} | met={o.met_primary_endpoint} | {o.indication}"
    if t == "market_metrics":
        s = getattr(o, "subject", a)
        return f"{s} | {o.metric} | {o.geography} | {o.value} {o.unit} | period={o.period}"
    return str(o)


@dataclass
class InspectItem:
    kind: str          # miss | false_positive | key_incomplete | attribute_error
    entity_type: str
    summary: str
    line_range: tuple[int, int] | None
    snippet: str
    detail: str = ""   # e.g. the attribute diff


@dataclass
class TypeScore:
    entity_type: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    key_incomplete: int = 0
    indication_verbose: int = 0
    items: list[InspectItem] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


# --------------------------------------------------------------------------- #
# Attribute scoring on matched pairs (key matched; these are non-key fields)
# --------------------------------------------------------------------------- #
def _attribute_errors(t: str, pred: Any, gold: Any, reporting_period: str | None) -> list[str]:
    # NB: therapeutic_area is open free-text BY DESIGN (no canonical taxonomy) and is therefore
    # NOT scored for accuracy — scoring it would impose a taxonomy via the golden bucket. It is
    # surfaced descriptively instead (see ta_disagreements). modality/target/primary_endpoint are
    # likewise open and not scored. indication stays a fuzzy KEY (it has real ground truth).
    errs: list[str] = []
    if t == "trials":
        if pred.met_primary_endpoint != gold.met_primary_endpoint:
            errs.append(f"met_primary_endpoint: pred={pred.met_primary_endpoint} vs gold={gold.met_primary_endpoint}")
    elif t == "regulatory_events":
        if not agency_attribute_matches(pred.agency, gold.agency):
            errs.append(f"agency: pred={pred.agency} vs gold={gold.agency}")
    elif t == "market_metrics":
        if not values_match(pred.value, pred.unit, gold.value, gold.unit):
            errs.append(f"value: pred={pred.value} {pred.unit} vs gold={gold.value} {gold.unit}")
        gp, pp = gold.period or reporting_period, pred.period if not is_null_sentinel(pred.period) else reporting_period
        if gp and canonical_term(pp) != canonical_term(gp):
            errs.append(f"period: pred={pred.period!r}(->{pp!r}) vs gold={gp!r}")
    return errs


# --------------------------------------------------------------------------- #
# Scoring one document
# --------------------------------------------------------------------------- #
def score_document(golden: GoldenDocument, result: Any, source_lines: list[str]) -> dict[str, Any]:
    pidx = build_asset_index(result.assets)
    all_g_assets = [a for c in golden.labeled_chunks for a in c.assets]
    gidx = build_golden_asset_index(all_g_assets)
    labeled = golden.labeled_chunk_indices()
    ranges = {tuple(c.line_range) for c in golden.labeled_chunks}

    # golden fact -> its chunk line_range (for miss provenance)
    g_prov: dict[int, tuple[int, int]] = {}
    for c in golden.labeled_chunks:
        for t in _FACT_TYPES:
            for f in getattr(c, t):
                g_prov[id(f)] = tuple(c.line_range)

    scores: dict[str, TypeScore] = {}
    ta_disagreements: list[InspectItem] = []
    for t in _FACT_TYPES:
        ts = TypeScore(t)
        raw = [f for f in getattr(result, t) if tuple(f.source_ref.line_range) in ranges]
        gold = [f for c in golden.labeled_chunks for f in getattr(c, t)]
        if t == "market_metrics":  # fold company self-reference before keying
            raw = [m.model_copy(update={"subject": fold_self_reference(m.subject, golden.source_company)}) for m in raw]
            gold = [m.model_copy(update={"subject": fold_self_reference(m.subject, golden.source_company)}) for m in gold]
        pin = _collapse_by_key(raw, lambda f, k=_PRED_KEYS[t]: k(f, pidx))
        gin = _collapse_by_key(gold, lambda f, k=_GOLD_KEYS[t]: k(f, gidx))
        out = match_lists(pin, gin, t, pidx, gidx)
        ts.tp, ts.fp, ts.fn = len(out.matched), len(out.false_positives), len(out.misses)
        ts.key_incomplete, ts.indication_verbose = len(out.key_incomplete), len(out.indication_verbose)

        for g in out.misses:
            ln, snip = _locate(source_lines, g_prov.get(id(g), (1, 1)), _g_keywords(t, g))
            ts.items.append(InspectItem("miss", t, _summary(t, g, True), (ln, ln), snip))
        for p in out.false_positives:
            ts.items.append(InspectItem("false_positive", t, _summary(t, p, False),
                                        tuple(p.source_ref.line_range), p.source_ref.snippet[:160]))
        for p in out.key_incomplete:
            ts.items.append(InspectItem("key_incomplete", t, _summary(t, p, False),
                                        tuple(p.source_ref.line_range), p.source_ref.snippet[:160]))
        for p in out.indication_verbose:
            ts.items.append(InspectItem("indication_verbose", t, _summary(t, p, False),
                                        tuple(p.source_ref.line_range), p.source_ref.snippet[:160],
                                        detail="right disease + extra qualifiers (no schema population/setting field)"))
        for p, g in out.matched:
            for diff in _attribute_errors(t, p, g, golden.reporting_period):
                ts.items.append(InspectItem("attribute_error", t, _summary(t, g, True),
                                            tuple(p.source_ref.line_range), p.source_ref.snippet[:120], diff))
            if t == "programs" and g.therapeutic_area and not fuzzy_match(p.therapeutic_area, g.therapeutic_area):
                ta_disagreements.append(InspectItem(
                    "ta_disagreement", t, _summary(t, g, True), tuple(p.source_ref.line_range),
                    p.source_ref.snippet[:120], f"pred TA={p.therapeutic_area!r} vs gold TA={g.therapeutic_area!r}"))
        scores[t] = ts

    return {
        "document_id": golden.document_id,
        "labeled_chunks": sorted(labeled),
        "scores": scores,
        "regulatory_grains": _regevent_grains(golden, result, pidx, gidx),
        "assets": _asset_report(golden, all_g_assets, pidx, gidx),
        "ta_disagreements": ta_disagreements,  # descriptive, NOT scored (open free-text field)
    }


# --------------------------------------------------------------------------- #
# Reg-event extra grains: standalone vs progress-row, and region-collapsed
# --------------------------------------------------------------------------- #
def _regevent_grains(golden: GoldenDocument, result: Any, pidx: AssetIndex, gidx: AssetIndex) -> dict[str, Any]:
    ranges = {tuple(c.line_range) for c in golden.labeled_chunks}
    raw = [f for f in result.regulatory_events if tuple(f.source_ref.line_range) in ranges]
    gold = [f for c in golden.labeled_chunks for f in c.regulatory_events]
    pin = _collapse_by_key(raw, lambda f: regevent_key(f, pidx))
    gin = _collapse_by_key(gold, lambda f: _g_regevent_key(f, gidx))
    out = match_lists(pin, gin, "regulatory_events", pidx, gidx)
    matched_g = {id(g) for _, g in out.matched}

    split = {"standalone": [0, 0], "progress_row": [0, 0]}
    for g in gin:
        k = "progress_row" if g.from_progress_row else "standalone"
        split[k][1] += 1
        split[k][0] += id(g) in matched_g

    # region-collapsed: drop region from the key so a 4-region sentence counts once
    def rc_pred(r):
        return (pidx.resolve(r.asset_id), r.action, canonical_term(r.indication))

    def rc_gold(g):
        return (gidx.resolve(slug(g.asset)), g.action, canonical_term(g.indication))
    pin_rc = _collapse_by_key(raw, rc_pred)
    gin_rc = _collapse_by_key(gold, rc_gold)
    matched_rc = 0
    used: set[int] = set()
    for g in gin_rc:
        gk = rc_gold(g)
        for i, p in enumerate(pin_rc):
            if i in used:
                continue
            if rc_pred(p) == gk:
                matched_rc += 1
                used.add(i)
                break
    return {
        "split": split,
        "region_split_recall": len(out.matched) / len(gin) if gin else 0.0,
        "region_collapsed": (matched_rc, len(gin_rc)),
    }


# --------------------------------------------------------------------------- #
# Assets: recall (labeled chunks) + over-merge diagnostic; precision withheld
# --------------------------------------------------------------------------- #
def _asset_report(golden: GoldenDocument, all_g_assets: list[Any], pidx: AssetIndex, gidx: AssetIndex) -> dict[str, Any]:
    # Dedup golden molecules by their own cluster so a molecule labeled in two chunks
    # (e.g. TAK-961 in chunks 12 and 14) counts once.
    distinct: list[Any] = []
    seen: set[str] = set()
    for a in all_g_assets:
        canon = gidx.resolve(slug(a.identifiers[0]))
        if canon not in seen:
            seen.add(canon)
            distinct.append(a)

    found, overmerge = 0, []
    cluster_to_golden: dict[str, list[str]] = {}
    for a in distinct:
        gs = {slug(x) for x in a.identifiers}
        hit = next((c for c in pidx.clusters if gs & c.slugs), None)
        found += hit is not None
        if hit is not None:
            cluster_to_golden.setdefault(hit.canonical, []).append(a.identifiers[0])
    for canon, names in cluster_to_golden.items():
        if len(names) > 1:  # distinct golden molecules sharing one predicted cluster
            overmerge.append({"predicted_cluster": canon, "golden_molecules": names})
    return {
        "recall_labeled": (found, len(distinct)),
        "precision": "withheld (document-level; full asset set not labeled)",
        "over_merge": overmerge,
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_markdown(reports: list[dict[str, Any]]) -> str:
    out: list[str] = ["# Extraction-accuracy report", ""]
    agg: dict[str, TypeScore] = {t: TypeScore(t) for t in _FACT_TYPES}
    for rep in reports:
        for t, ts in rep["scores"].items():
            agg[t].tp += ts.tp; agg[t].fp += ts.fp; agg[t].fn += ts.fn
            agg[t].key_incomplete += ts.key_incomplete; agg[t].indication_verbose += ts.indication_verbose

    out.append("## Aggregate (all labeled chunks)")
    out.append("| type | TP | FP | FN | KI | IV | P | R | F1 |")
    out.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|")
    for t in _FACT_TYPES:
        s = agg[t]
        out.append(f"| {t} | {s.tp} | {s.fp} | {s.fn} | {s.key_incomplete} | {s.indication_verbose} | "
                   f"{s.precision:.2f} | {s.recall:.2f} | {s.f1:.2f} |")
    out.append("")

    for rep in reports:
        out.append(f"## {rep['document_id']}  (chunks {rep['labeled_chunks']})")
        g = rep["regulatory_grains"]
        st, pr = g["split"]["standalone"], g["split"]["progress_row"]
        rc = g["region_collapsed"]
        out.append(f"- reg-events — standalone {st[0]}/{st[1]} R={st[0]/st[1] if st[1] else 0:.2f}; "
                   f"progress-row {pr[0]}/{pr[1]} R={pr[0]/pr[1] if pr[1] else 0:.2f}; "
                   f"region-collapsed {rc[0]}/{rc[1]} R={rc[0]/rc[1] if rc[1] else 0:.2f}")
        a = rep["assets"]
        out.append(f"- assets — recall {a['recall_labeled'][0]}/{a['recall_labeled'][1]}; precision {a['precision']}")
        for om in a["over_merge"]:
            out.append(f"    OVER-MERGE: predicted cluster '{om['predicted_cluster']}' = golden {om['golden_molecules']}")
        tad = rep.get("ta_disagreements", [])
        if tad:
            out.append(f"- therapeutic_area disagreements (descriptive, NOT scored): {len(tad)}")
            for it in tad:
                out.append(f"    L{it.line_range[0]} {it.summary.split(' | ')[0]}: {it.detail}")
        out.append("")
        for t in _FACT_TYPES:
            items = rep["scores"][t].items
            if not items:
                continue
            out.append(f"### {rep['document_id']} · {t}")
            for it in items:
                lr = f"L{it.line_range[0]}-{it.line_range[1]}" if it.line_range else "L?"
                extra = f"  [{it.detail}]" if it.detail else ""
                out.append(f"- **{it.kind}** {lr}: {it.summary}{extra}")
                out.append(f"    ↳ {it.snippet}")
            out.append("")
    return "\n".join(out)
