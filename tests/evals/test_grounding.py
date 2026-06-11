"""Tests for src/evals/grounding.py — per-token containment + category split."""

from src.evals.grounding import ground_fact
from src.schema import Program, RegulatoryEvent, SourceRef, Trial

SOURCE = [
    "TAK-1 Multiple Indications Japan Approved (Feb 2026)",   # 1
    "ADCETRIS Front line Hodgkin lymphoma EU approval",       # 2
    "filler line with no facts",                              # 3
    "Systemic lupus erythematosus 2028 3",                    # 4 (bare-number phase/stage)
]


def _sr(lr, snippet="snip"):
    return SourceRef(document_id="d", line_range=lr, snippet=snippet)


def _reg(asset_id, action, region, indication, lr, snippet="snip"):
    return RegulatoryEvent(asset_id=asset_id, agency="MHLW", region=region, action=action,
                           indication=indication, source_ref=_sr(lr, snippet))


def _cat(r, name):
    return next(c.category for c in r.checks if c.name == name)


def test_closed_enum_synonym_grounds():
    r = ground_fact(_reg("tak-1", "approval", "JP", "Multiple Indications", (1, 1)), "regulatory_events", SOURCE)
    assert _cat(r, "asset") == "grounded"
    assert _cat(r, "action") == "grounded"   # 'approval' <- 'Approved'
    assert _cat(r, "region") == "grounded"   # 'JP' <- 'Japan'


def test_line_range_load_bearing_not_snippet():
    r = ground_fact(_reg("adcetris", "approval", "EU", "Front line Hodgkin lymphoma", (2, 2),
                         snippet="## unrelated fallback chunk text " * 8), "regulatory_events", SOURCE)
    assert _cat(r, "action") == "grounded"   # decided by line 2, not the snippet
    assert r.snippet_fallback


def test_real_failure_when_not_in_cited_lines():
    r = ground_fact(_reg("tak-1", "approval", "JP", "Multiple Indications", (3, 3)), "regulatory_events", SOURCE)
    assert _cat(r, "asset") == "real_failure"
    assert _cat(r, "action") == "real_failure"


def test_region_inferred_when_no_region_word():
    # line 4 has no region word; a fact asserting region=Global -> 'inferred', not real_failure.
    p = Program(id="p", asset_id="vay736", therapeutic_area="immunology", indication="Systemic lupus erythematosus",
                region="Global", stage="P3", as_of_date="2026", source_ref=_sr((4, 4)))
    r = ground_fact(p, "programs", SOURCE)
    assert _cat(r, "region") == "inferred"


def test_map_gap_on_bare_number_phase():
    # source encodes phase as bare '3'; the map won't bridge it -> 'map_gap', not a fault.
    t = Trial(id="t", trial_name=None, asset_ids=["vay736"], indication="Systemic lupus erythematosus",
              phase="3", source_ref=_sr((4, 4)))
    r = ground_fact(t, "trials", SOURCE)
    assert _cat(r, "phase") == "map_gap"
    assert _cat(r, "asset") == "real_failure"  # 'vay736' not on line 4
