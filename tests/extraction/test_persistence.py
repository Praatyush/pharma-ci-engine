"""Tests for src/extraction/persistence.py — ExtractionResult <-> JSON round-trip.

No key, no network: the result is built from the same in-memory payload->schema
mapping the extractor uses, then persisted and reloaded from a tmp path.
"""

import json

import pytest

from src.extraction import extractor
from src.extraction.models import (
    ChunkExtraction,
    ExtractedAsset,
    ExtractedMarketMetric,
    ExtractedProgram,
    ExtractedRegulatoryEvent,
    ExtractedTrial,
)
from src.extraction.persistence import (
    SCHEMA_VERSION,
    count_by_type,
    load_extraction,
    save_extraction,
)
from src.ingestion.chunker import Chunk


def _result():
    """One of each entity type, grounded — via the extractor's own mapping."""
    chunk = Chunk(
        document_id="takeda-doc",
        chunk_index=2,
        section_path=["Oncology"],
        line_range=(10, 23),
        text="zasocitinib | Psoriasis P-III US\n",
    )
    payload = ChunkExtraction(
        assets=[
            ExtractedAsset(
                generic_name="zasocitinib",
                development_codes=["TAK-279"],
                modality="small_molecule",
                evidence="zasocitinib | Psoriasis P-III US",
            )
        ],
        programs=[
            ExtractedProgram(
                asset_ref="zasocitinib",
                therapeutic_area="immunology",
                indication="Psoriasis",
                region="US",
                stage="P3",
                evidence="zasocitinib | Psoriasis P-III US",
            )
        ],
        trials=[
            ExtractedTrial(asset_refs=["zasocitinib"], indication="CLL", phase="3", evidence="x")
        ],
        regulatory_events=[
            ExtractedRegulatoryEvent(
                asset_ref="TAK-755", agency="FDA", region="US", action="breakthrough",
                indication="cTTP", evidence="y",
            )
        ],
        market_metrics=[
            ExtractedMarketMetric(
                subject_ref="Takeda", metric="revenue", value=1234.0, unit="USD million",
                period="Q4 FY2025", geography="Global", evidence="z",
            )
        ],
    )
    return extractor._map_payload(payload, chunk, source_company="Takeda", as_of_date="2026-05-13")


def test_round_trip_preserves_every_entity(tmp_path):
    original = _result()
    path = save_extraction(tmp_path / "sub" / "out.json", original, meta={"k": "v"})
    assert path.exists()  # parent dirs created

    meta, loaded = load_extraction(path)
    assert meta == {"k": "v"}
    for name in ("assets", "programs", "trials", "regulatory_events", "market_metrics"):
        before = [o.model_dump() for o in getattr(original, name)]
        after = [o.model_dump() for o in getattr(loaded, name)]
        assert before == after, name


def test_round_trip_preserves_grounding_line_range(tmp_path):
    # line_range is a tuple[int, int]; JSON makes it a list -> must coerce back to tuple.
    path = save_extraction(tmp_path / "out.json", _result(), meta={})
    _, loaded = load_extraction(path)
    assert loaded.programs[0].source_ref.line_range == (10, 23)


def test_artifact_header_has_version_and_counts(tmp_path):
    path = save_extraction(tmp_path / "out.json", _result(), meta={})
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == SCHEMA_VERSION
    assert artifact["counts"] == count_by_type(_result())
    assert artifact["counts"]["programs"] == 1


def test_load_rejects_unknown_schema_version(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": "999", "result": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        load_extraction(path)
