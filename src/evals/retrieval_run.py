"""A2b / Gate A — wire the chunk-leg retriever (A2a) into the shared scorer (A1), score every
scored golden query, and emit the Stage-A sliced recall@k report + the containment distribution
that resolves the T-decision (`docs/RETRIEVAL_PLAN.md` §A.6).

    python -m src.evals.retrieval_run

This JOINS two already-verified components and changes neither: it imports
``src.rag.chunk_leg`` (A2a, eyeball-verified) and ``src.evals.retrieval_scorer`` (A1, verified
10/10), converts each retrieved ``RetrievalUnit`` to the scorer's ``Unit``, and scores. One
overlap implementation (`retrieval_scorer.line_containment`) is reused for the distribution. The
report is the Gate-A artifact: it is REVIEWED before anything follows — this module does not tune,
does not pick a final T, and does not start Stage B.
"""

import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.rag.chunk_leg import INDEX_DIR, RETRIEVAL_CHUNK_CONFIG, build_or_load
from src.rag.fusion import K_RRF

from .retrieval_scorer import DEFAULT_T, Unit, _construct_base, line_containment, score_query

_GOLDEN = Path("src/evals/golden/retrieval.golden.json")
_OUT_DIR = Path("data/eval/reports")
_KS = [1, 3, 5, 10]
_DEPTH = 10  # operating retrieval depth for the containment distribution (the deepest reported k)


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _golden_spans(q: dict[str, Any]) -> list[dict[str, Any]]:
    """Every golden span of a query (facts / comparison members / aggregate rows), with resolution."""
    spans: list[dict[str, Any]] = []
    for f in q.get("facts", []):
        spans += [{**s, "_owner": f.get("fact_id", "?")} for s in f.get("spans", [])]
    for m in q.get("member_facts", []):
        spans += [{**s, "_owner": m.get("asset", m.get("member_id", "?"))} for s in m.get("spans", [])]
    for r in q.get("aggregate", {}).get("row_set", []):
        spans.append({"doc_id": r["doc_id"], "line_range": r["line_range"], "resolution": "clean",
                      "_owner": r.get("asset", "row")})
    return spans


def _recall_fraction(sc: Any, base: str, k: int) -> tuple[int, int]:
    """Construct-appropriate (hit, total) at top-k, read off the scorer's QueryScore."""
    if base == "aggregate":
        return sc.recall_by_k[k]
    if base == "comparison":
        return sc.attribute            # per-asset attribute coverage = comparison's recall axis
    return (sc.n_hit, sc.n_total)      # single / set-of-singles


def build_report() -> tuple[dict[str, Any], str]:
    retr = build_or_load()  # loads the A2a index from data/rag (built once; not rebuilt)
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    queries = [q for q in golden["queries"] if q.get("scored", True)]  # 9 scored (Q2 §7-excluded)
    n_units = len(retr.units)

    per_query: list[dict[str, Any]] = []
    # accumulators for slices
    type_recall: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    slice_recall: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    head_recall: dict[int, list[float]] = defaultdict(list)
    head_recall_T99: dict[int, list[float]] = defaultdict(list)
    containment_vals: list[dict[str, Any]] = []

    for q in queries:
        base = _construct_base(q.get("construct"))
        retrieved = retr.retrieve(q["query"], k=n_units)  # full ranked list
        ranked_units = [Unit(u.doc_id, u.line_range) for u, _ in retrieved]
        ranked_keys = [(u.doc_id, u.line_range) for u, _ in retrieved]

        # recall@k (and a T=0.99 pass for the T-invariance check)
        recall_k: dict[int, tuple[int, int]] = {}
        presence_k: dict[int, tuple[int, int]] = {}
        if base == "aggregate":
            sc_all = score_query(q, ranked_units, DEFAULT_T, ks=_KS)
            sc_all99 = score_query(q, ranked_units, 0.99, ks=_KS)
            for k in _KS:
                recall_k[k] = sc_all.recall_by_k[k]
                head_recall_T99[k].append(_frac(sc_all99.recall_by_k[k]))
        else:
            for k in _KS:
                sc = score_query(q, ranked_units[:k], DEFAULT_T)
                sc99 = score_query(q, ranked_units[:k], 0.99)
                recall_k[k] = _recall_fraction(sc, base, k)
                if base == "comparison":
                    presence_k[k] = sc.presence
                head_recall_T99[k].append(_frac(_recall_fraction(sc99, base, k)))

        for k in _KS:
            f = _frac(recall_k[k])
            head_recall[k].append(f)
            type_recall[base][k].append(f)
            slice_recall[q.get("slice", "?")][k].append(f)

        # RL slice (clean-vs-RL split; §5) at the operating depth
        rl = score_query(q, ranked_units[:_DEPTH], DEFAULT_T, ks=_KS).rl_slice

        # per-span: containing-chunk rank (full list) + max containment over top-DEPTH
        span_detail = []
        for s in _golden_spans(q):
            doc, lr = s["doc_id"], (s["line_range"][0], s["line_range"][1])
            rank = next((i for i, key in enumerate(ranked_keys, 1)
                         if key[0] == doc and key[1][0] <= lr[0] and lr[1] <= key[1][1]), None)
            maxc = max((line_containment(doc, lr, ranked_units[j]) for j in range(min(_DEPTH, len(ranked_units)))),
                       default=0.0)
            span_detail.append({"owner": s["_owner"], "doc_id": doc, "line_range": list(lr),
                                "resolution": s.get("resolution", "clean"),
                                "containing_chunk_rank": rank, "max_containment_top%d" % _DEPTH: round(maxc, 3)})
            containment_vals.append({"query": q["id"], "owner": s["_owner"], "resolution": s.get("resolution", "clean"),
                                     "max_containment": round(maxc, 3), "containing_chunk_rank": rank})

        clean_ranks = [d["containing_chunk_rank"] for d in span_detail
                       if d["resolution"] != "resolution_limited" and d["containing_chunk_rank"]]
        per_query.append({
            "id": q["id"], "type": q["type"], "construct": base, "slice": q.get("slice", "?"),
            "recall_at_k": {k: f"{recall_k[k][0]}/{recall_k[k][1]}" for k in _KS},
            "presence_at_k": {k: f"{presence_k[k][0]}/{presence_k[k][1]}" for k in _KS} if presence_k else None,
            "best_clean_containing_rank": min(clean_ranks) if clean_ranks else None,
            "rl_slice": rl,
            "spans": span_detail,
        })

    # containment distribution + verdict
    approx1 = sum(1 for c in containment_vals if c["max_containment"] >= 0.99)
    approx0 = sum(1 for c in containment_vals if c["max_containment"] <= 0.01)
    fractional = [c for c in containment_vals if 0.01 < c["max_containment"] < 0.99]
    head99 = {k: round(_mean(head_recall_T99[k]), 4) for k in _KS}
    head50 = {k: round(_mean(head_recall[k]), 4) for k in _KS}
    t_invariant = head50 == head99

    report = {
        "meta": {
            "report": "phase-3-gate-A", "generated_at": datetime.now(timezone.utc).isoformat(),
            "git_sha": _git_sha(), "embed_model": retr.dense.meta["embed_model"],
            "k_rrf": K_RRF, "chunk_config": {"chunk_size": RETRIEVAL_CHUNK_CONFIG.chunk_size,
                                             "overlap": RETRIEVAL_CHUNK_CONFIG.overlap},
            "T": DEFAULT_T, "retrieval_depth_for_distribution": _DEPTH,
            "corpus_units": n_units, "scored_queries": len(queries),
        },
        "recall_at_k": {
            "headline_macro": head50,
            "by_type": {t: {k: round(_mean(type_recall[t][k]), 4) for k in _KS} for t in type_recall},
            "by_slice": {s: {k: round(_mean(slice_recall[s][k]), 4) for k in _KS} for s in slice_recall},
        },
        "t_decision": {
            "headline_T0.5": head50, "headline_T0.99": head99, "recall_T_invariant": t_invariant,
            "containment_distribution": {"approx_1.0": approx1, "approx_0.0": approx0,
                                         "fractional_count": len(fractional), "fractional_cases": fractional,
                                         "total_spans": len(containment_vals)},
            "verdict": ("T is STRUCTURALLY INERT at chunk grain: containment is degenerate-bimodal "
                        "(≈1.0/≈0.0), so recall@k is threshold-independent for sub-chunk spans. No final "
                        "T is pinned here; the T-decision is made in review on this data."
                        if not fractional and t_invariant else
                        "Fractional containment cases EXIST (listed) — these are where T would bite; "
                        "review them to pin a meaningful T."),
        },
        "per_query": per_query,
    }
    return report, _render(report)


def _frac(ht: tuple[int, int]) -> float:
    h, t = ht
    return h / t if t else 0.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _render(r: dict[str, Any]) -> str:
    m = r["meta"]
    out = ["# Phase 3 — Gate A: chunk-leg retrieval scored against the golden", ""]
    out.append(f"- generated {m['generated_at']} · git_sha {m['git_sha']} · embed `{m['embed_model']}` · "
               f"k_rrf {m['k_rrf']} · chunk {m['chunk_config']} · T {m['T']} · {m['corpus_units']} units · "
               f"{m['scored_queries']} scored queries")
    out.append("")
    out.append("## Recall@k — headline (macro-avg over scored queries)")
    out.append("| k | recall |\n|---|---|")
    for k in _KS:
        out.append(f"| {k} | {r['recall_at_k']['headline_macro'][k]:.3f} |")
    out.append("")
    out.append("## Sliced by query TYPE (never merged — §6)")
    out.append("| type | @1 | @3 | @5 | @10 |\n|---|---|---|---|---|")
    for t, d in sorted(r["recall_at_k"]["by_type"].items()):
        out.append(f"| {t} | " + " | ".join(f"{d[k]:.3f}" for k in _KS) + " |")
    out.append("\n> aggregate (Q4) low recall = the locked aggregate-dilution finding (sparse-TA rows in mixed-TA chunks); reported, not fixed.")
    out.append("")
    out.append("## Sliced by extracted / un-extracted (§6)")
    out.append("| slice | @1 | @3 | @5 | @10 |\n|---|---|---|---|---|")
    for s, d in sorted(r["recall_at_k"]["by_slice"].items()):
        out.append(f"| {s} | " + " | ".join(f"{d[k]:.3f}" for k in _KS) + " |")
    out.append("\n> at chunk grain the chunk leg reaches both slices; this contrast becomes load-bearing in Stage B (entity leg).")
    out.append("")
    td = r["t_decision"]
    cd = td["containment_distribution"]
    out.append("## T-decision (§A.6) — containment distribution over top-%d" % m["retrieval_depth_for_distribution"])
    out.append(f"- spans: **{cd['approx_1.0']} ≈1.0**, **{cd['approx_0.0']} ≈0.0**, "
               f"**{cd['fractional_count']} fractional** (of {cd['total_spans']} total)")
    out.append(f"- recall@k T-invariant (T=0.5 vs T=0.99): **{td['recall_T_invariant']}**")
    if cd["fractional_cases"]:
        out.append("- fractional cases (where T would bite):")
        for c in cd["fractional_cases"]:
            out.append(f"    - {c['query']} {c['owner']} containment={c['max_containment']} (rank {c['containing_chunk_rank']})")
    out.append(f"- **VERDICT:** {td['verdict']}")
    out.append("")
    out.append("## Per-query")
    out.append("| Q | type | construct | slice | recall@1/3/5/10 | best clean chunk rank | notes |\n|---|---|---|---|---|---|---|")
    for p in r["per_query"]:
        rk = "/".join(p["recall_at_k"][k].split("/")[0] for k in _KS) + f" (of {p['recall_at_k'][10].split('/')[1]})"
        note = ""
        if p["presence_at_k"]:
            note = f"presence@10 {p['presence_at_k'][10]}"
        if p["rl_slice"]:
            note += (" · " if note else "") + f"RL-slice {p['rl_slice']}"
        out.append(f"| {p['id']} | {p['type']} | {p['construct']} | {p['slice']} | {rk} | "
                   f"{p['best_clean_containing_rank']} | {note} |")
    out.append("")
    out.append("_Gate A artifact — for review. No tuning, no final T, no Stage B performed._")
    return "\n".join(out)


def main() -> None:
    if not (INDEX_DIR / "chunks.faiss").exists():
        print(f"NOTE: no index at {INDEX_DIR}; build_or_load will build it once.")
    report, markdown = build_report()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    (_OUT_DIR / "retrieval_gate_a.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (_OUT_DIR / "retrieval_gate_a.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\nWrote {_OUT_DIR / 'retrieval_gate_a.md'} and {_OUT_DIR / 'retrieval_gate_a.json'}")


if __name__ == "__main__":
    main()
