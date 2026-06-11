"""A1 shared-retrieval-scorer tests: containment arithmetic, clean/RL split (§5),
T-sweepability (§2), and reproduction of the labeling-pass numbers from the golden's
recorded stand-in units (the A1 gate)."""

from src.evals.retrieval_scorer import (
    DEFAULT_T,
    _GOLDEN,
    Unit,
    _verify,
    line_containment,
    score_fact,
    score_span,
)


# --------------------------------------------------------------------------- #
# §2 containment — the single overlap function
# --------------------------------------------------------------------------- #
def test_line_containment_arithmetic():
    assert line_containment("d", (10, 12), Unit("d", (1, 100))) == 1.0   # span fully inside unit
    assert line_containment("d", (10, 19), Unit("d", (10, 14))) == 0.5   # 5 of 10 span lines inside
    assert line_containment("d", (10, 12), Unit("d", (20, 30))) == 0.0   # disjoint
    assert line_containment("d", (5, 5), Unit("d", (5, 5))) == 1.0       # single line


def test_containment_is_doc_gated():
    # same line numbers, different document -> no overlap (cross-doc keying, §6)
    assert line_containment("takeda", (10, 12), Unit("novartis", (1, 100))) == 0.0


def test_T_is_sweepable_not_baked_in():
    span = {"doc_id": "d", "line_range": [10, 19]}          # 10 lines
    units = [Unit("d", (10, 15))]                            # covers 6 -> containment 0.6
    assert score_span(span, units, 0.5).hit is True          # 0.6 >= 0.5
    assert score_span(span, units, 0.7).hit is False         # 0.6 <  0.7


# --------------------------------------------------------------------------- #
# §5 resolution — clean vs resolution_limited, never silently upgraded
# --------------------------------------------------------------------------- #
def test_clean_and_rl_span_split():
    spans = [
        {"doc_id": "d", "line_range": [10, 12], "resolution": "clean"},
        {"doc_id": "d", "line_range": [50, 60], "resolution": "resolution_limited"},
    ]
    # only the RL span is covered -> RL hit, NOT a clean hit
    rl_only = score_fact(spans, [Unit("d", (45, 65))], DEFAULT_T)
    assert rl_only.clean_hit is False and rl_only.rl_hit is True
    # the clean span is covered -> clean hit
    clean = score_fact(spans, [Unit("d", (8, 15))], DEFAULT_T)
    assert clean.clean_hit is True
    # both covered -> clean hit AND rl flagged (Q3's actual situation)
    both = score_fact(spans, [Unit("d", (8, 15)), Unit("d", (45, 65))], DEFAULT_T)
    assert both.clean_hit is True and both.rl_hit is True


# --------------------------------------------------------------------------- #
# The A1 gate — reproduce the labeling-pass numbers from the golden's stand-in units
# --------------------------------------------------------------------------- #
def test_reproduces_labeling_pass_numbers():
    rows, all_pass = _verify(_GOLDEN, DEFAULT_T)
    assert all_pass, [r for r in rows if not r[3]]


def test_containment_bimodal_so_T_invariant_on_golden():
    # stand-in spans sit fully inside their stand-in chunks (1.0) or are absent (0.0):
    # bimodal containment -> identical verdicts across any T in (0, 1] (the locked finding).
    _, pass_low = _verify(_GOLDEN, 0.01)
    _, pass_high = _verify(_GOLDEN, 0.99)
    assert pass_low and pass_high
