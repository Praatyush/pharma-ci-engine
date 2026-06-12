"""Shared retrieval scorer — Phase 3 Stage A, sub-step A1.

Leg-agnostic: consumes a *ranked list of retrieval ``Unit``s* (each a
``(doc_id, line_range)``) and one query loaded from ``retrieval.golden.json``, and
produces the §3 construct score + sliced recall. It knows nothing about HOW the units
were retrieved (chunk leg, entity leg, or fused) — that is exactly what lets Stage A2
run it three ways (chunk / entity / fused) without change.

Design (``docs/RETRIEVAL_PLAN.md``; relevance policy v2 embedded in the golden):

- **§2 containment** = ``|span_lines ∩ unit_lines| / |span_lines|`` — answer-coverage
  direction, ``doc_id``-gated (cross-document keying). ``T`` is a **sweepable parameter**,
  never baked in.
- **§5 resolution** — a hit via a ``resolution_limited``-only span is reported in a
  separate RL slice and **never folded into clean recall**; a fact with a clean-span hit
  is a clean hit even if an RL span also hits.
- **§3 constructs** (dispatched on the query's ``construct`` field): ``single`` /
  ``set-of-singles`` (OR-of-locations per fact; all facts required) / ``comparison``
  (TWO scores — presence + attribute, never collapsed) / ``aggregate`` (recall-fraction
  over the row-set).
- **§6 slicing** — extracted vs un-extracted, never merged. **§7** — ``scored:false``
  queries (Q2 Avidity) are excluded from every denominator.

**One overlap implementation.** ``line_containment`` below is the single line-interval
overlap used by all retrieval scoring (both legs). NOTE: ``grounding.py`` has no
line-*interval* overlap to reuse — its ``_cited_text`` returns *text* for token-presence
grounding, a different computation. See the A1 build report; this is not a second copy of
an existing function.
"""

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Policy v2 provisional T (docs/RETRIEVAL_PLAN.md §A.6). Sweepable — never baked in.
DEFAULT_T = 0.5

_GOLDEN = Path("src/evals/golden/retrieval.golden.json")


@dataclass(frozen=True)
class Unit:
    """A retrieval unit the scorer overlap-tests against golden spans.

    Leg-agnostic: a chunk unit (ingestion chunk) or an entity unit (a fact's SourceRef)
    — both expose ``(doc_id, line_range)``. ``line_range`` is 1-based inclusive.
    """

    doc_id: str
    line_range: tuple[int, int]


def line_containment(span_doc_id: str, span_line_range: tuple[int, int], unit: Unit) -> float:
    """§2 containment: fraction of the span's lines that fall inside the unit.

    Answer-coverage direction (how much of the *answer* the unit covers), ``doc_id``-gated
    so a line_range never matches across documents. The ONE retrieval-overlap function.
    """
    if unit.doc_id != span_doc_id:
        return 0.0
    sa, sb = span_line_range
    ua, ub = unit.line_range
    intersection = max(0, min(sb, ub) - max(sa, ua) + 1)
    span_len = sb - sa + 1
    return intersection / span_len if span_len > 0 else 0.0


@dataclass
class SpanResult:
    doc_id: str
    line_range: tuple[int, int]
    resolution: str  # 'clean' | 'resolution_limited'
    containment: float
    hit: bool


def score_span(span: dict[str, Any], units: list[Unit], t: float) -> SpanResult:
    """Best containment of one golden span over the ranked units; HIT iff >= t."""
    doc = span["doc_id"]
    rng = (span["line_range"][0], span["line_range"][1])
    best = 0.0
    for u in units:
        c = line_containment(doc, rng, u)
        if c > best:
            best = c
    return SpanResult(doc, rng, span.get("resolution", "clean"), best, best >= t)


@dataclass
class FactOutcome:
    """OR-of-locations over a fact's spans, split clean vs resolution_limited (§5)."""

    clean_hit: bool   # a CLEAN span reached >= t -> counts toward clean recall
    rl_hit: bool      # an RL span reached >= t -> RL slice only, never clean
    spans: list[SpanResult] = field(default_factory=list)


def score_fact(spans: list[dict[str, Any]], units: list[Unit], t: float) -> FactOutcome:
    """A fact HITS (clean) iff any of its CLEAN span locations is covered >= t."""
    results = [score_span(s, units, t) for s in spans]
    clean_hit = any(r.hit for r in results if r.resolution != "resolution_limited")
    rl_hit = any(r.hit for r in results if r.resolution == "resolution_limited")
    return FactOutcome(clean_hit, rl_hit, results)


@dataclass
class QueryScore:
    """Construct-appropriate score for one query. Only the relevant fields are filled."""

    query_id: str
    construct: str
    scored: bool
    # single / set-of-singles:
    recall: float | None = None
    n_hit: int | None = None
    n_total: int | None = None
    # comparison:
    presence: tuple[int, int] | None = None
    attribute: tuple[int, int] | None = None
    attribute_sliced: dict[str, tuple[int, int]] | None = None
    # aggregate:
    recall_by_k: dict[int, tuple[int, int]] | None = None
    # cross-cutting:
    rl_slice: list[str] = field(default_factory=list)  # fact ids whose RL span hit (§5)
    note: str = ""


def _construct_base(construct: str | None) -> str:
    """Map the golden's construct label to a handler key (e.g. 'single (per-region facts)' -> 'single')."""
    if not construct:
        return "none"
    c = construct.strip().lower()
    if c.startswith("set-of-singles"):
        return "set-of-singles"
    if c.startswith("single"):
        return "single"
    if c.startswith("comparison"):
        return "comparison"
    if c.startswith("aggregate"):
        return "aggregate"
    return c


def _score_facts(facts: list[dict[str, Any]], units: list[Unit], t: float) -> tuple[int, int, list[str]]:
    """Clean recall over a list of facts (single / set-of-singles); RL-slice fact ids."""
    n_hit, rl = 0, []
    for f in facts:
        out = score_fact(f["spans"], units, t)
        if out.clean_hit:
            n_hit += 1
        if out.rl_hit:
            rl.append(f.get("fact_id", "?"))
    return n_hit, len(facts), rl


def _score_comparison(query: dict[str, Any], units: list[Unit], t: float) -> QueryScore:
    members = query["member_facts"]
    # presence: each entity satisfied if ANY of its assets clean-hits (AND across entities)
    present: dict[str, bool] = {}
    for m in members:
        present.setdefault(m["entity"], False)
    # attribute: per asset; sliced by member slice
    attr_hit = 0
    sliced: dict[str, list[int]] = {}
    for m in members:
        out = score_fact(m["spans"], units, t)
        if out.clean_hit:
            present[m["entity"]] = True
            attr_hit += 1
        sl = sliced.setdefault(m["slice"], [0, 0])
        sl[1] += 1
        if out.clean_hit:
            sl[0] += 1
    return QueryScore(
        query_id=query["id"], construct="comparison", scored=True,
        presence=(sum(present.values()), len(present)),
        attribute=(attr_hit, len(members)),
        attribute_sliced={k: (v[0], v[1]) for k, v in sliced.items()},
    )


def _score_aggregate(query: dict[str, Any], units: list[Unit], t: float, ks: list[int]) -> QueryScore:
    rows = query["aggregate"]["row_set"]
    by_k: dict[int, tuple[int, int]] = {}
    for k in ks:
        topk = units[:k]
        hits = sum(1 for r in rows if score_span(r, topk, t).hit)
        by_k[k] = (hits, len(rows))
    return QueryScore(query_id=query["id"], construct="aggregate", scored=True, recall_by_k=by_k)


def score_query(query: dict[str, Any], units: list[Unit], t: float = DEFAULT_T,
                ks: list[int] | None = None) -> QueryScore:
    """Score one golden query against a ranked unit list. Dispatch on the construct field.

    ``units`` is already ranked (best first). For ``aggregate`` the recall curve is computed
    over top-``k`` for each ``k`` in ``ks`` (default {1,3,5,10}); other constructs evaluate
    over the full list (recall@k for them = truncate ``units`` before calling).
    """
    if not query.get("scored", True):
        return QueryScore(query["id"], _construct_base(query.get("construct")), scored=False,
                          note=f"excluded ({query.get('excluded', {}).get('rule', '§7')})")
    base = _construct_base(query.get("construct"))
    if base in ("single", "set-of-singles"):
        n_hit, n_total, rl = _score_facts(query["facts"], units, t)
        return QueryScore(query["id"], base, scored=True, n_hit=n_hit, n_total=n_total,
                          recall=(n_hit / n_total if n_total else 0.0), rl_slice=rl)
    if base == "comparison":
        return _score_comparison(query, units, t)
    if base == "aggregate":
        return _score_aggregate(query, units, t, ks or [1, 3, 5, 10])
    return QueryScore(query["id"], base, scored=True, note="unhandled construct")


# --------------------------------------------------------------------------- #
# A1 verification harness — reproduce the labeling-pass numbers from the golden's
# OWN recorded stand-in units. (This is harness code, NOT the leg-agnostic scorer:
# it reconstructs the stand-in unit lists the labeling pass used. A2 will instead
# feed real retrieved units.)
# --------------------------------------------------------------------------- #
def _all_spans(query: dict[str, Any]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for f in query.get("facts", []):
        spans += f.get("spans", [])
    for m in query.get("member_facts", []):
        spans += m.get("spans", [])
    spans += query.get("aggregate", {}).get("row_set", [])
    return spans


def _doc_for_range(rng: tuple[int, int], spans: list[dict[str, Any]]) -> str | None:
    """doc_id of any golden span contained in ``rng`` (how the labeling pass placed a stand-in)."""
    a, b = rng
    for s in spans:
        sa, sb = s["line_range"]
        if a <= sa and sb <= b:
            return s["doc_id"]
    return None


def standin_units(query: dict[str, Any]) -> list[Unit]:
    """Reconstruct the RANKED stand-in unit list the labeling pass used for this query."""
    base = _construct_base(query.get("construct"))
    spans = _all_spans(query)
    if base == "aggregate":  # units = the row chunks, ranked by #rows covered (desc)
        rows = query["aggregate"]["row_set"]
        counts: dict[tuple[str, tuple[int, int]], int] = {}
        for r in rows:
            key = (r["doc_id"], (r["chunk"][0], r["chunk"][1]))
            counts[key] = counts.get(key, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        return [Unit(doc, rng) for (doc, rng), _ in ranked]
    if base == "comparison":
        raw = query["comparison"]["attribute_coverage"]["stand_in_units"]
    else:
        raw = query["stand_in_retrieval"]["units"]
    units: list[Unit] = []
    for a, b in raw:
        doc = _doc_for_range((a, b), spans)
        if doc is None:
            raise ValueError(f"{query['id']}: stand-in unit {(a, b)} contains no golden span (cannot place doc_id)")
        units.append(Unit(doc, (a, b)))
    return units


# Expected labeling-pass numbers (hand-computed in the labeling pass; the A1 gate).
_EXPECTED: dict[str, dict[str, Any]] = {
    "Q1": {"kind": "single", "recall": (4, 4), "rl": 0},
    "Q3": {"kind": "single", "recall": (3, 3), "rl": 3},  # clean via progress; RL via main-table
    "Q4": {"kind": "aggregate", "recall@1": (7, 8), "recall@2": (8, 8)},
    "Q5": {"kind": "comparison", "presence": (2, 2), "attribute": (3, 4),
           "sliced": {"extracted": (3, 3), "un-extracted": (0, 1)}},
    "Q6": {"kind": "single", "recall": (1, 1), "rl": 0},
    "Q7": {"kind": "single", "recall": (1, 1), "rl": 0},
    "Q8": {"kind": "single", "recall": (1, 1), "rl": 0},
    "Q9": {"kind": "single", "recall": (1, 1), "rl": 0},
    "Q10": {"kind": "single", "recall": (1, 1), "rl": 0},
    "Q2": {"kind": "excluded"},
}


def _verify(golden_path: Path, t: float) -> tuple[list[tuple[str, str, str, bool]], bool]:
    data = json.loads(golden_path.read_text(encoding="utf-8"))
    rows: list[tuple[str, str, str, bool]] = []
    all_pass = True
    for q in data["queries"]:
        qid = q["id"]
        exp = _EXPECTED.get(qid, {})
        if exp.get("kind") == "excluded" or not q.get("scored", True):
            ok = not q.get("scored", True)
            rows.append((qid, "excluded (§7, no denominator)", "scored=false", ok))
            all_pass &= ok
            continue
        units = standin_units(q)
        if exp["kind"] == "aggregate":
            sc = score_query(q, units, t, ks=[1, 2])
            got1, got2 = sc.recall_by_k[1], sc.recall_by_k[2]
            ok = got1 == exp["recall@1"] and got2 == exp["recall@2"]
            got = f"recall@1={got1[0]}/{got1[1]}({got1[0]/got1[1]:.3f}), recall@2={got2[0]}/{got2[1]}({got2[0]/got2[1]:.3f})"
            want = f"recall@1={exp['recall@1'][0]}/{exp['recall@1'][1]}(0.875), recall@2={exp['recall@2'][0]}/{exp['recall@2'][1]}(1.000)"
        elif exp["kind"] == "comparison":
            sc = score_query(q, units, t)
            ok = (sc.presence == exp["presence"] and sc.attribute == exp["attribute"]
                  and sc.attribute_sliced == exp["sliced"])
            got = f"presence={sc.presence[0]}/{sc.presence[1]}, attribute={sc.attribute[0]}/{sc.attribute[1]}, sliced={ _fmt_sliced(sc.attribute_sliced) }"
            want = f"presence=2/2, attribute=3/4, sliced=ext 3/3, un-ext 0/1"
        else:  # single / set-of-singles
            sc = score_query(q, units, t)
            ok = ((sc.n_hit, sc.n_total) == exp["recall"] and len(sc.rl_slice) == exp["rl"])
            got = f"recall={sc.n_hit}/{sc.n_total}({sc.recall:.3f}), rl_slice={len(sc.rl_slice)}"
            want = f"recall={exp['recall'][0]}/{exp['recall'][1]}, rl_slice={exp['rl']}"
        rows.append((qid, f"got: {got}", f"want: {want}", ok))
        all_pass &= ok
    return rows, all_pass


def _fmt_sliced(s: dict[str, tuple[int, int]] | None) -> str:
    if not s:
        return "-"
    return ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(s.items()))


def main() -> None:
    p = argparse.ArgumentParser(description="A1 verification: reproduce labeling-pass numbers from stand-in units.")
    p.add_argument("--golden", type=Path, default=_GOLDEN)
    p.add_argument("--t", type=float, default=DEFAULT_T, help="containment threshold (sweepable)")
    args = p.parse_args()

    rows, all_pass = _verify(args.golden, args.t)
    width = max(len(r[1]) for r in rows)
    print(f"A1 shared-scorer verification  (T={args.t}, golden={args.golden})\n")
    for qid, got, want, ok in rows:
        print(f"  [{'PASS' if ok else 'FAIL'}] {qid:<4} {got:<{width}}   {want}")
    print(f"\n{'ALL PASS' if all_pass else 'FAILURES PRESENT'} — {sum(r[3] for r in rows)}/{len(rows)} checks passed")


if __name__ == "__main__":
    main()
