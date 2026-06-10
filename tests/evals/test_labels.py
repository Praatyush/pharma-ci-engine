"""Tests for src/evals/labels.py — golden label schema + loader.

The example below is a *format* fixture (a few facts taken from the real Novartis
slice artifact, chunk 32), not the actual golden set.
"""

import json

import pytest

from src.evals.labels import GOLDEN_SCHEMA_VERSION, GoldenDocument, load_golden

# A minimal but representative golden file: one labeled chunk, one of each fact type.
EXAMPLE = {
    "golden_schema_version": "1",
    "document_id": "q1-2026-interim-financial-report-en",
    "source_company": "Novartis",
    "artifact": "q1-2026-interim-financial-report-en.slice.extraction.json",
    "reporting_period": "Q1 2026",
    "as_of_date": "2026-03-31",
    "labeled_chunks": [
        {
            "chunk_index": 32,
            "line_range": [1065, 1127],
            "note": "ianalumab pipeline + a sample revenue line",
            "assets": [
                {"identifiers": ["ianalumab", "VAY736"], "modality": "mAb", "target": "BAFF-R"}
            ],
            "programs": [
                {
                    "asset": "ianalumab",
                    "indication": "Systemic lupus erythematosus",
                    "region": "Global",
                    "stage": "P3",
                    "therapeutic_area": "immunology",
                }
            ],
            "trials": [
                {
                    "trial_name": "VAYHIA",
                    "assets": ["ianalumab"],
                    "indication": "Warm autoimmune hemolytic anemia",
                    "phase": "3",
                    "met_primary_endpoint": False,
                }
            ],
            "regulatory_events": [
                {
                    "asset": "ianalumab",
                    "action": "breakthrough",
                    "indication": "Sjogren's disease",
                    "region": "US",
                    "agency": "FDA",
                }
            ],
            "market_metrics": [
                {
                    "subject": "Entresto",
                    "metric": "revenue",
                    "geography": "Global",
                    "value": 1.3,
                    "unit": "billion",
                    "currency": "USD",
                    "period": "Q1 2026",
                }
            ],
        }
    ],
}


def _write(tmp_path, data) -> str:
    p = tmp_path / "novartis.golden.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_loads_and_validates_example(tmp_path):
    gold = load_golden(_write(tmp_path, EXAMPLE))
    assert isinstance(gold, GoldenDocument)
    chunk = gold.labeled_chunks[0]
    assert gold.labeled_chunk_indices() == {32}
    assert chunk.assets[0].identifiers == ["ianalumab", "VAY736"]
    assert chunk.trials[0].met_primary_endpoint is False
    assert chunk.market_metrics[0].unit == "billion"
    # version constant is what the loader enforces
    assert gold.golden_schema_version == GOLDEN_SCHEMA_VERSION


def test_rejects_unknown_version(tmp_path):
    bad = {**EXAMPLE, "golden_schema_version": "999"}
    with pytest.raises(ValueError, match="golden_schema_version"):
        load_golden(_write(tmp_path, bad))


def test_rejects_bad_closed_enum(tmp_path):
    bad = json.loads(json.dumps(EXAMPLE))
    bad["labeled_chunks"][0]["programs"][0]["stage"] = "Phase 3"  # not a ProgramStage value
    with pytest.raises(ValueError):
        load_golden(_write(tmp_path, bad))


def test_rejects_unknown_field(tmp_path):
    bad = json.loads(json.dumps(EXAMPLE))
    bad["labeled_chunks"][0]["programs"][0]["stagee"] = "P3"  # typo'd key
    with pytest.raises(ValueError):
        load_golden(_write(tmp_path, bad))


def test_asset_requires_an_identifier(tmp_path):
    bad = json.loads(json.dumps(EXAMPLE))
    bad["labeled_chunks"][0]["assets"][0]["identifiers"] = []
    with pytest.raises(ValueError):
        load_golden(_write(tmp_path, bad))


def test_duplicate_chunk_index_rejected(tmp_path):
    bad = json.loads(json.dumps(EXAMPLE))
    bad["labeled_chunks"].append(json.loads(json.dumps(bad["labeled_chunks"][0])))
    with pytest.raises(ValueError, match="duplicate chunk_index"):
        load_golden(_write(tmp_path, bad))
