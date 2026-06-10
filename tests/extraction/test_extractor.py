"""Tests for src/extraction/extractor.py — payload->schema mapping + grounding.

The Gemini call is monkeypatched; no key, no network, no live call.
"""

from src.extraction import extractor
from src.extraction.models import (
    ChunkExtraction,
    ExtractedAsset,
    ExtractedMarketMetric,
    ExtractedProgram,
    ExtractedRegulatoryEvent,
    ExtractedTrial,
)
from src.ingestion.chunker import Chunk
from src.schema import Asset, MarketMetric, Program, RegulatoryEvent, SourceRef, Trial

CHUNK_TEXT = (
    "## Oncology\n"
    "zasocitinib | Psoriasis P-III US\n"
    "TAK-755 received FDA breakthrough designation in cTTP\n"
    "Phase 3 SEQUOIA trial in CLL met primary endpoint (PFS)\n"
    "Net sales 1234 USD million\n"
)


def _chunk() -> Chunk:
    return Chunk(
        document_id="takeda-doc",
        chunk_index=2,
        section_path=["Oncology"],
        line_range=(10, 23),
        text=CHUNK_TEXT,
    )


def _payload() -> ChunkExtraction:
    return ChunkExtraction(
        assets=[
            ExtractedAsset(
                generic_name="zasocitinib",
                development_codes=["TAK-279"],
                modality="small_molecule",
                evidence="zasocitinib | Psoriasis P-III US",
            ),
            ExtractedAsset(  # no identifier at all -> must be skipped
                company="Takeda", evidence="(none)"
            ),
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
            ExtractedTrial(
                asset_refs=["zanubrutinib"],
                indication="CLL",
                phase="3",
                trial_name="SEQUOIA",
                primary_endpoint="PFS",
                met_primary_endpoint=True,
                evidence="Phase 3 SEQUOIA trial in CLL met primary endpoint (PFS)",
            )
        ],
        regulatory_events=[
            ExtractedRegulatoryEvent(
                asset_ref="TAK-755",
                agency="FDA",
                region="US",
                action="breakthrough",
                indication="cTTP",
                evidence="TAK-755 received FDA breakthrough designation in cTTP",
            )
        ],
        market_metrics=[
            ExtractedMarketMetric(
                subject_ref="Takeda",
                metric="revenue",
                value=1234.0,
                unit="USD million",
                period="Q4 FY2025",
                geography="Global",
                evidence="Net sales 1234 USD million",
            )
        ],
    )


def _map():
    return extractor._map_payload(
        _payload(), _chunk(), source_company="Takeda", as_of_date="2026-05-13"
    )


def test_entities_built_for_each_type():
    res = _map()
    assert len(res.assets) == 1  # the identifier-less asset was skipped
    assert len(res.programs) == 1
    assert len(res.trials) == 1
    assert len(res.regulatory_events) == 1
    assert len(res.market_metrics) == 1
    assert isinstance(res.assets[0], Asset)
    assert isinstance(res.programs[0], Program)
    assert isinstance(res.trials[0], Trial)
    assert isinstance(res.regulatory_events[0], RegulatoryEvent)
    assert isinstance(res.market_metrics[0], MarketMetric)


def test_every_fact_carries_grounded_source_ref():
    res = _map()
    facts = [res.programs[0], res.trials[0], res.regulatory_events[0], res.market_metrics[0]]
    for fact in facts:
        ref = fact.source_ref
        assert isinstance(ref, SourceRef)
        assert ref.document_id == "takeda-doc"
        assert ref.line_range == (10, 23)        # load-bearing, from the chunk
        assert ref.as_of_date == "2026-05-13"


def test_snippet_uses_verbatim_evidence_when_present():
    res = _map()
    # the program's evidence is a verbatim substring of the chunk -> used as-is
    assert res.programs[0].source_ref.snippet == "zasocitinib | Psoriasis P-III US"


def test_snippet_falls_back_to_chunk_when_evidence_not_verbatim():
    chunk = _chunk()
    payload = ChunkExtraction(
        programs=[
            ExtractedProgram(
                asset_ref="x",
                therapeutic_area="oncology",
                indication="y",
                region="US",
                stage="P1",
                evidence="THIS QUOTE IS NOT IN THE CHUNK",
            )
        ]
    )
    res = extractor._map_payload(payload, chunk, source_company="Takeda", as_of_date="2026-05-13")
    assert res.programs[0].source_ref.snippet == chunk.text[:600]


def test_asset_company_defaults_to_source_company():
    res = _map()
    assert res.assets[0].company == "Takeda"  # payload asset had no company


def test_asset_id_and_linking_use_slug():
    res = _map()
    assert res.assets[0].id == "zasocitinib"
    assert res.programs[0].asset_id == "zasocitinib"   # links to the asset
    assert res.trials[0].asset_ids == ["zanubrutinib"]  # dangling ref ok (deferred)
    assert res.regulatory_events[0].asset_id == "tak-755"


def test_program_as_of_date_defaults_to_document_snapshot():
    res = _map()
    assert res.programs[0].as_of_date == "2026-05-13"


def test_extract_chunk_uses_generate_structured(monkeypatch):
    captured = {}

    def fake_generate(contents, response_schema, *, system_instruction, temperature):
        captured["contents"] = contents
        captured["schema"] = response_schema
        captured["temperature"] = temperature
        captured["system_instruction"] = system_instruction
        return _payload()

    monkeypatch.setattr(extractor, "generate_structured", fake_generate)
    res = extractor.extract_chunk(_chunk(), source_company="Takeda", as_of_date="2026-05-13")

    assert captured["contents"] == CHUNK_TEXT
    assert captured["schema"] is ChunkExtraction
    assert captured["temperature"] == 0.0
    assert captured["system_instruction"] == extractor.EXTRACTION_SYSTEM_PROMPT
    assert len(res.programs) == 1


def test_extract_document_concatenates_without_dedup(monkeypatch):
    # same payload for every chunk -> duplicates accumulate (by design)
    monkeypatch.setattr(extractor, "generate_structured", lambda *a, **k: _payload())
    chunks = [_chunk(), _chunk(), _chunk()]
    res = extractor.extract_document(chunks, source_company="Takeda", as_of_date="2026-05-13")
    assert len(res.assets) == 3  # 1 valid asset per chunk x 3, no dedup
    assert len(res.programs) == 3
