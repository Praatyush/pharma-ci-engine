"""Tests for src/evals/run.py — report assembly (pure helpers + integration smoke)."""

from pathlib import Path

import pytest

from src.evals import run as R
from src.extraction.extractor import ExtractionResult
from src.schema import RegulatoryEvent, SourceRef


def _reg(lr):
    return RegulatoryEvent(asset_id="x", agency="FDA", region="US", action="filed",
                           indication="y", source_ref=SourceRef(document_id="d", line_range=lr, snippet="s"))


def test_plasma_line_counts_per_chunk():
    res = ExtractionResult(regulatory_events=[_reg((537, 618)), _reg((807, 860)), _reg((807, 860))])
    out = R._plasma_line([(537, 618), (734, 806), (807, 860)], res)
    assert out == [((537, 618), 1), ((734, 806), 0), ((807, 860), 2)]


def test_render_emits_required_sections():
    report = {
        "meta": {"generated_at": "t", "git_sha": "abc", "golden_schema_version": "1", "judge_model": None,
                 "documents": [{"document_id": "doc", "scope": "FULLY CENSUSED", "extraction_model": "m",
                                "prompt_sha256": "p"}]},
        "plasma_localization": {"doc": [("537-618", 0), ("807-860", 1)]},
        "grounding": {"by_token": {"asset": {"grounded": 98, "real_failure": 2},
                                   "region": {"grounded": 60, "inferred": 11, "real_failure": 29}},
                      "snippet_fallback": [156, 307]},
    }
    md = R._render(report, [])  # empty reps -> aggregate renders as zeros
    assert "Plasma localization" in md
    assert "Grounding" in md
    assert "FULLY CENSUSED" in md            # scope statement present
    assert "judge_model: None" in md
    assert "inferred" in md                  # region inferred broken out


@pytest.mark.skipif(not Path("data/eval/extractions").exists(), reason="extraction artifacts not present")
def test_build_report_integration():
    report, md = R.build_report()
    assert "phase-2-baseline" == report["meta"]["report"]
    assert report["meta"]["judge_model"] is None
    assert set(report["scores"]) and "Phase 2 Baseline" in md
    # decomposed program precision: clean FP excludes restatement
    prog = next(iter(report["scores"].values()))["programs"]
    assert "restatement" in prog
