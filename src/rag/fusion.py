"""Reciprocal Rank Fusion — the locked score-combination (no normalization, no weight).

``RRF(d) = Σ_legs 1/(k_rrf + rank_leg(d))`` with ``rank`` 1-based. A unit present in only
one leg's list contributes only that leg's term (no penalty, no imputation). Rank-based by
design: it needs no score normalization and exposes **no tunable weight** — the locked
α-avoidance (a weighted fusion's α is uncalibrable on this golden, the same reason the
containment threshold T is deferred; see ``docs/RETRIEVAL_PLAN.md``).
"""

K_RRF = 60  # locked default


def rrf(ranked_lists: list[list[int]], k_rrf: int = K_RRF) -> list[tuple[int, float]]:
    """Fuse per-leg ranked id lists (each best-first) into one ranked (id, score) list."""
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, unit_id in enumerate(ranked, start=1):
            scores[unit_id] = scores.get(unit_id, 0.0) + 1.0 / (k_rrf + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
