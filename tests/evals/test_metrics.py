"""Tests for src/evals/metrics.py — union scoping, P/R/F1, key-incomplete, provenance."""

from src.evals.labels import GoldenDocument
from src.evals.metrics import score_document
from src.extraction.extractor import ExtractionResult
from src.schema import Asset, Program, RegulatoryEvent, SourceRef

SOURCE_LINES = [
    "TAK-1 oncology program row",      # 1
    "TAK-1 gastric cancer P3 US",      # 2
    "TAK-2 received breakthrough",     # 3
]


def _sr(lr):
    return SourceRef(document_id="d", line_range=lr, snippet="snip")


def _golden():
    return GoldenDocument.model_validate({
        "golden_schema_version": "1", "document_id": "d", "source_company": "Takeda",
        "artifact": "d.json", "reporting_period": "FY2025 Q4",
        "labeled_chunks": [{
            "chunk_index": 0, "line_range": [1, 3],
            "assets": [{"identifiers": ["TAK-1"]}, {"identifiers": ["TAK-2"]}],
            "programs": [{"asset": "TAK-1", "indication": "gastric cancer", "region": "US", "stage": "P3"}],
            "regulatory_events": [
                {"asset": "TAK-2", "action": "breakthrough", "indication": "gastric cancer",
                 "region": "US", "agency": "FDA", "from_progress_row": False},
            ],
        }],
    })


def _result():
    return ExtractionResult(
        assets=[Asset(id="tak-1", development_codes=["TAK-1"], company="Takeda"),
                Asset(id="tak-2", development_codes=["TAK-2"], company="Takeda")],
        programs=[Program(id="p", asset_id="tak-1", therapeutic_area="oncology", indication="gastric cancer",
                          region="US", stage="P3", as_of_date="2026", source_ref=_sr((1, 3)))],
        regulatory_events=[
            # under-specified: indication is the null sentinel -> key_incomplete, not FP
            RegulatoryEvent(asset_id="tak-2", agency="FDA", region="US", action="breakthrough",
                            indication="not specified", source_ref=_sr((1, 3))),
        ],
    )


def test_scores_and_key_incomplete():
    rep = score_document(_golden(), _result(), SOURCE_LINES)
    prog, reg = rep["scores"]["programs"], rep["scores"]["regulatory_events"]
    assert (prog.tp, prog.fp, prog.fn) == (1, 0, 0) and prog.precision == 1.0
    # the designation lost its indication -> key_incomplete, golden stays a miss, no clean FP
    assert reg.tp == 0 and reg.fn == 1 and reg.key_incomplete == 1 and reg.fp == 0


def test_miss_items_carry_provenance():
    rep = score_document(_golden(), _result(), SOURCE_LINES)
    misses = [it for it in rep["scores"]["regulatory_events"].items if it.kind == "miss"]
    assert misses and misses[0].line_range[0] == 3      # located TAK-2's line
    assert "TAK-2" in misses[0].snippet


def test_asset_recall_reported_precision_withheld():
    rep = score_document(_golden(), _result(), SOURCE_LINES)
    assert rep["assets"]["recall_labeled"] == (2, 2)
    assert "withheld" in rep["assets"]["precision"]
