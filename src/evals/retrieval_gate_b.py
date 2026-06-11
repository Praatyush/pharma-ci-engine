"""Gate B (and Gate B-revised) — chunk / entity / fused decomposition, scored by the SHARED scorer
(A1, unchanged) against the golden.

    python -m src.evals.retrieval_gate_b

Reports FOUR legs so the fusion fix is legible against the naive baseline in one artifact:
``chunk_only``, ``entity_only``, ``fused_naive`` (the Gate-B disjoint-set interleave), and
``fused_revised`` (RRF keyed on the span ``(doc_id, line_range)`` — the parameter-free fusion fix in
``rag.fusion.rrf_fuse_by_span``). The fix touches ONLY cross-leg fusion: ``chunk_only`` must
reproduce Gate A and ``entity_only`` / ``fused_naive`` must reproduce Gate B — if any moves, this
STOPS (the fix leaked outside fusion). No tuning, no chunk-config change, no winner picked.
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.rag.chunk_leg import build_or_load
from src.rag.entity_leg import SERIALIZATION, build_or_load_entity
from src.rag.fusion import K_RRF, rrf_fuse_by_span

from .retrieval_run import _KS, _frac, _git_sha, _mean, _recall_fraction
from .retrieval_scorer import DEFAULT_T, Unit, _construct_base, score_query

_GOLDEN = Path("src/evals/golden/retrieval.golden.json")
_OUT_DIR = Path("data/eval/reports")
_LEGS = ["chunk_only", "entity_only", "fused_naive", "fused_revised"]

# Reproduction guards (the fix is fusion-only; these legs must NOT move). Tolerance absorbs
# display-rounding (≤0.001); real drift would be ≥ ~0.014. Values are the committed Gate-A / Gate-B
# headline macro recall@{1,3,5,10}.
_EXPECTED = {
    "chunk_only": {1: 0.518, 3: 0.741, 5: 0.741, 10: 0.903},   # Gate A
    "entity_only": {1: 0.569, 3: 0.893, 5: 0.935, 10: 0.972},  # Gate B
    "fused_naive": {1: 0.518, 3: 0.755, 5: 0.893, 10: 0.935},  # Gate B (naive fusion)
}
_TOL = 0.005


def _fuse_naive(chunk_ret: list, entity_ret: list, k_rrf: int) -> list:
    """The Gate-B naive cross-leg fusion: RRF over DISJOINT unit sets (each unit its own slot)."""
    scored = [(1.0 / (k_rrf + r), "c", u) for r, (u, _) in enumerate(chunk_ret, 1)]
    scored += [(1.0 / (k_rrf + r), "e", u) for r, (u, _) in enumerate(entity_ret, 1)]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [u for _, _, u in scored]


def _score_curve(q: dict, ranked_units: list[Unit], base: str) -> dict[int, tuple[int, int]]:
    out: dict[int, tuple[int, int]] = {}
    if base == "aggregate":
        sc = score_query(q, ranked_units, DEFAULT_T, ks=_KS)
        for k in _KS:
            out[k] = sc.recall_by_k[k]
    else:
        for k in _KS:
            out[k] = _recall_fraction(score_query(q, ranked_units[:k], DEFAULT_T), base, k)
    return out


def _first_covering(doc: str, lr: tuple[int, int], units: list) -> tuple[int | None, Any]:
    a, b = lr
    for i, u in enumerate(units, 1):
        if u.doc_id == doc and u.line_range[0] <= a and b <= u.line_range[1]:
            return i, u
    return None, None


def build_report() -> tuple[dict[str, Any], str]:
    chunk = build_or_load()
    entity = build_or_load_entity()
    golden = {q["id"]: q for q in json.loads(_GOLDEN.read_text(encoding="utf-8"))["queries"]}
    queries = [q for q in golden.values() if q.get("scored", True)]

    head = {leg: defaultdict(list) for leg in _LEGS}
    by_type = {leg: defaultdict(lambda: defaultdict(list)) for leg in _LEGS}
    by_slice = {leg: defaultdict(lambda: defaultdict(list)) for leg in _LEGS}
    per_query, raw = [], {}

    for q in queries:
        base = _construct_base(q["construct"])
        c_ret = chunk.retrieve(q["query"], len(chunk.units))
        e_ret = entity.retrieve(q["query"], len(entity.units))
        ru_chunk = [u for u, _ in c_ret]
        ru_entity = [u for u, _ in e_ret]
        ru = {
            "chunk_only": ru_chunk,
            "entity_only": ru_entity,
            "fused_naive": _fuse_naive(c_ret, e_ret, K_RRF),
            "fused_revised": rrf_fuse_by_span([ru_chunk, ru_entity], K_RRF),
        }
        raw[q["id"]] = ru
        ranked = {leg: [Unit(u.doc_id, u.line_range) for u in ru[leg]] for leg in _LEGS}
        curves = {leg: _score_curve(q, ranked[leg], base) for leg in _LEGS}
        for leg in _LEGS:
            for k in _KS:
                f = _frac(curves[leg][k])
                head[leg][k].append(f)
                by_type[leg][base][k].append(f)
                by_slice[leg][q.get("slice", "?")][k].append(f)
        per_query.append({"id": q["id"], "type": q["type"], "construct": base, "slice": q.get("slice", "?"),
                          "recall": {leg: {k: f"{curves[leg][k][0]}/{curves[leg][k][1]}" for k in _KS} for leg in _LEGS}})

    head_raw = {leg: {k: _mean(head[leg][k]) for k in _KS} for leg in _LEGS}
    reproduces = {leg: all(abs(head_raw[leg][k] - _EXPECTED[leg][k]) <= _TOL for k in _KS) for leg in _EXPECTED}

    delta_revised = {t: {k: round(_mean(by_type["fused_revised"][t][k]) - _mean(by_type["chunk_only"][t][k]), 4) for k in _KS}
                     for t in by_type["fused_revised"]}
    delta_naive = {t: {k: round(_mean(by_type["fused_naive"][t][k]) - _mean(by_type["chunk_only"][t][k]), 4) for k in _KS}
                   for t in by_type["fused_naive"]}

    report = {
        "meta": {"report": "phase-3-gate-B-revised", "generated_at": datetime.now(timezone.utc).isoformat(),
                 "git_sha": _git_sha(), "embed": chunk.dense.meta["embed_model"], "k_rrf": K_RRF, "T": DEFAULT_T,
                 "chunk_units": len(chunk.units), "entity_units": len(entity.units), "serialization": SERIALIZATION,
                 "fusion_fix": "rrf_fuse_by_span — cross-leg RRF keyed on (doc_id, line_range); parameter-free"},
        "reproduction_guards": {leg: {"raw": {k: round(head_raw[leg][k], 6) for k in _KS},
                                      "expected": _EXPECTED[leg], "match_within_tol": reproduces[leg]} for leg in _EXPECTED},
        "all_guards_pass": all(reproduces.values()),
        "recall_at_k": {leg: {"headline": {k: round(_mean(head[leg][k]), 4) for k in _KS},
                              "by_type": {t: {k: round(_mean(by_type[leg][t][k]), 4) for k in _KS} for t in by_type[leg]},
                              "by_slice": {s: {k: round(_mean(by_slice[leg][s][k]), 4) for k in _KS} for s in by_slice[leg]}}
                        for leg in _LEGS},
        "entity_delta_recall_by_type": {"fused_revised_minus_chunk": delta_revised, "fused_naive_minus_chunk": delta_naive},
        "locked_prediction_cases": _cases(golden, raw),
        "per_query": per_query,
    }
    return report, _render(report)


def _cases(golden: dict, raw: dict) -> dict[str, Any]:
    def ranks(qid: str, doc: str, lr: tuple[int, int]) -> dict[str, Any]:
        out = {}
        for leg in _LEGS:
            r, u = _first_covering(doc, lr, raw[qid][leg])
            out[leg] = {"rank": r, "unit_text": (u.text[:78] if u else None)}
        return out

    q5 = golden["Q5"]
    members = {m["asset"]: m for m in q5["member_facts"]}
    van = members["Vanrafia (atrasentan)"]["spans"][0]
    q5_assets = {name: ranks("Q5", members[name]["spans"][0]["doc_id"],
                             (members[name]["spans"][0]["line_range"][0], members[name]["spans"][0]["line_range"][1]))
                 for name in ["mezagitamab (TAK-079)", "Fabhalta (iptacopan)", "zigakibart (FUB523)"]}
    q1 = golden["Q1"]
    q1_spans = {f["fact_id"]: ranks("Q1", f["spans"][0]["doc_id"], (f["spans"][0]["line_range"][0], f["spans"][0]["line_range"][1]))
                for f in q1["facts"]}
    return {
        "vanrafia_negative_control": {"span": [van["doc_id"], van["line_range"]],
                                      "ranks": ranks("Q5", van["doc_id"], (van["line_range"][0], van["line_range"][1])),
                                      "naive_fused_rank": 11, "chunk_only_rank": 6},
        "q5_buried_extracted_assets": {"ranks": q5_assets, "naive_fused": {"mezagitamab": 10, "Fabhalta": 2, "zigakibart": 4}},
        "q1_plasma_mistyped_as_stage": {"ranks": q1_spans},
    }


def _row(d: dict[int, float]) -> str:
    return " | ".join(f"{d[k]:.3f}" for k in _KS)


def _render(r: dict[str, Any]) -> str:
    m = r["meta"]
    o = ["# Phase 3 — Gate B-revised: parameter-free fusion fix (RRF keyed on span)", ""]
    o.append(f"- generated {m['generated_at']} · git_sha {m['git_sha']} · k_rrf {m['k_rrf']} · T {m['T']} · "
             f"chunk {m['chunk_units']} / entity {m['entity_units']} units")
    o.append(f"- fusion fix: **{m['fusion_fix']}**")
    g = r["reproduction_guards"]
    o.append(f"- **reproduction guards (fix is fusion-only): all pass = {r['all_guards_pass']}** — "
             + "; ".join(f"{leg} {'OK' if g[leg]['match_within_tol'] else 'MOVED!'}" for leg in g))
    o.append("")
    o.append("## Recall@k by query TYPE — four legs (§6, never merged)")
    for leg in _LEGS:
        o.append(f"\n**{leg}** (headline @1/3/5/10: {_row(r['recall_at_k'][leg]['headline'])})")
        o.append("| type | @1 | @3 | @5 | @10 |\n|---|---|---|---|---|")
        for t, d in sorted(r["recall_at_k"][leg]["by_type"].items()):
            o.append(f"| {t} | {_row(d)} |")
    o.append("")
    o.append("## Entity Δrecall@k by type — fused_revised vs fused_naive (both − chunk-only)")
    o.append("| type | revised Δ@1/3/5/10 | naive Δ@1/3/5/10 |\n|---|---|---|")
    dv, dn = r["entity_delta_recall_by_type"]["fused_revised_minus_chunk"], r["entity_delta_recall_by_type"]["fused_naive_minus_chunk"]
    for t in sorted(dv):
        o.append(f"| {t} | " + " ".join(f"{dv[t][k]:+.3f}" for k in _KS) + " | " + " ".join(f"{dn[t][k]:+.3f}" for k in _KS) + " |")
    o.append("")
    c = r["locked_prediction_cases"]
    o.append("## The fix measurement — locked-prediction cases (rank per leg)")
    v = c["vanrafia_negative_control"]
    o.append(f"\n**1. Vanrafia (target — recover unique reach)** span {v['span']}  ·  chunk-only {v['chunk_only_rank']}, naive-fused {v['naive_fused_rank']}")
    for leg in _LEGS:
        o.append(f"   - {leg}: rank {v['ranks'][leg]['rank']}")
    o.append(f"   - HEADLINE: did fused_revised recover Vanrafia into top-10? "
             f"{'YES' if (v['ranks']['fused_revised']['rank'] or 99) <= 10 else 'NO'} "
             f"(rank {v['ranks']['fused_revised']['rank']}; was 11 naive)")
    o.append(f"\n**2. Q5 three buried extracted IgAN assets** (naive-fused: mezagitamab 10 / Fabhalta 2 / zigakibart 4)")
    for name, rk in c["q5_buried_extracted_assets"]["ranks"].items():
        o.append(f"   - {name}: chunk {rk['chunk_only']['rank']} · entity {rk['entity_only']['rank']} · "
                 f"naive {rk['fused_naive']['rank']} · **revised {rk['fused_revised']['rank']}**")
    o.append(f"\n**3. Q1 plasma (mistyped-as-stage)**")
    for fid, rk in c["q1_plasma_mistyped_as_stage"]["ranks"].items():
        o.append(f"   - {fid}: chunk {rk['chunk_only']['rank']} · entity {rk['entity_only']['rank']} · "
                 f"naive {rk['fused_naive']['rank']} · revised {rk['fused_revised']['rank']}")
    o.append("")
    o.append("## Per-query recall@k (chunk / entity / fused_naive / fused_revised)")
    o.append("| Q | type | slice | chunk | entity | fused_naive | fused_revised |\n|---|---|---|---|---|---|---|")
    for p in r["per_query"]:
        def row(leg):
            return "/".join(p["recall"][leg][k].split("/")[0] for k in _KS) + f"(/{p['recall'][leg][10].split('/')[1]})"
        o.append(f"| {p['id']} | {p['type']} | {p['slice']} | {row('chunk_only')} | {row('entity_only')} | {row('fused_naive')} | {row('fused_revised')} |")
    o.append("\n_Gate B-revised artifact — for review. Parameter-free fusion fix; no tuning, no winner picked._")
    return "\n".join(o)


def main() -> None:
    report, markdown = build_report()
    if not report["all_guards_pass"]:
        print("STOP: a fusion-only fix moved chunk_only / entity_only / fused_naive — the fix leaked. Report NOT written.")
        print(json.dumps(report["reproduction_guards"], indent=2))
        return
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    (_OUT_DIR / "retrieval_gate_b_revised.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (_OUT_DIR / "retrieval_gate_b_revised.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\nWrote {_OUT_DIR / 'retrieval_gate_b_revised.md'} and {_OUT_DIR / 'retrieval_gate_b_revised.json'}")


if __name__ == "__main__":
    main()
