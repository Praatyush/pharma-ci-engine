"""Reciprocal Rank Fusion — the locked score-combination (no normalization, no weight).

``RRF(d) = Σ_legs 1/(k_rrf + rank_leg(d))`` with ``rank`` 1-based. A unit present in only
one leg's list contributes only that leg's term (no penalty, no imputation). Rank-based by
design: it needs no score normalization and exposes **no tunable weight** — the locked
α-avoidance (a weighted fusion's α is uncalibrable on this golden, the same reason the
containment threshold T is deferred; see ``docs/RETRIEVAL_PLAN.md``).
"""

from typing import Any

K_RRF = 60  # locked default


def rrf(ranked_lists: list[list[int]], k_rrf: int = K_RRF) -> list[tuple[int, float]]:
    """Fuse per-leg ranked id lists (each best-first) into one ranked (id, score) list.

    Used WITHIN a leg to fuse its dense + BM25 lists (same unit set, ints index that set).
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, unit_id in enumerate(ranked, start=1):
            scores[unit_id] = scores.get(unit_id, 0.0) + 1.0 / (k_rrf + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def rrf_fuse_by_span(legs: list[list[Any]], k_rrf: int = K_RRF) -> list[Any]:
    """Cross-leg RRF keyed on the SPAN ``(doc_id, line_range)`` — the evidence identity the scorer
    overlap-tests — NOT on opaque per-leg unit objects.

    Why this is the fix (Gate-B finding): an entity unit's ``line_range`` is its source *chunk's*
    range, and the chunk leg ranks every chunk, so a chunk unit and the entity units from that chunk
    are **co-located at the identical span**. Naive cross-leg fusion treated them as distinct items,
    so each consumed a separate top-k slot (~50/50 interleave) and displaced the chunk leg's unique
    reach. Keying RRF on the span makes co-located units **collapse to one fused entry** (each leg
    contributes its **best/min rank** for that span; agreement across legs sums), so they no longer
    double-consume slots.

    **Parameter-free:** the only "value" is the structural span key ``(doc_id, line_range)``; there is
    no leg weight, no cutoff, no N to tune. ``k_rrf`` is the locked RRF rank constant, not a weight.
    ``legs`` = list of per-leg ranked unit lists (best-first); returns one fused ranked unit list
    (one representative unit per distinct span).
    """
    score: dict[tuple[str, tuple[int, int]], float] = {}
    rep: dict[tuple[str, tuple[int, int]], Any] = {}
    for ranked in legs:
        seen_this_leg: set[tuple[str, tuple[int, int]]] = set()
        for rank, u in enumerate(ranked, start=1):
            key = (u.doc_id, u.line_range)
            if key in seen_this_leg:        # this leg already counted its best (min) rank for the span
                continue
            seen_this_leg.add(key)
            score[key] = score.get(key, 0.0) + 1.0 / (k_rrf + rank)
            rep.setdefault(key, u)          # representative is span-only relevant to the scorer
    return [rep[k] for k in sorted(score, key=lambda kk: score[kk], reverse=True)]
