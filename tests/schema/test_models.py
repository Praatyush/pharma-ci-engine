"""Tests for the domain schema (src/schema). Mirrors src/schema under tests/.

Covers, per the 7 entities: valid construction, closed-enum rejection,
open-vocab pass-through, required-field enforcement (incl. the mandatory
``source_ref`` on every fact entity), and serialization round-trips.
"""

import pytest
from pydantic import ValidationError

from src.schema import (
    Asset,
    Document,
    MarketMetric,
    Program,
    RegulatoryEvent,
    SourceRef,
    Trial,
)


def make_source_ref(**overrides) -> SourceRef:
    """A valid SourceRef for reuse by the fact-entity tests."""
    data = dict(
        document_id="doc-1",
        section="Oncology pipeline",
        line_range=(120, 145),
        snippet="zanubrutinib — Phase 3 in CLL",
        as_of_date="2026-05-13",
    )
    data.update(overrides)
    return SourceRef(**data)


# --------------------------------------------------------------------------- #
# Valid construction for each model
# --------------------------------------------------------------------------- #
def test_document_valid():
    doc = Document(
        id="doc-1",
        source_company="Takeda",
        title="Q4 FY2025 Pipeline Table",
        doc_type="pipeline_table",
    )
    assert doc.doc_type == "pipeline_table"
    # unmarked-optional fields default to None
    assert doc.url is None
    assert doc.period_covered is None


def test_source_ref_valid():
    ref = make_source_ref()
    assert ref.document_id == "doc-1"
    assert ref.line_range == (120, 145)
    assert ref.page is None  # flexible locator fields are optional


def test_asset_valid():
    asset = Asset(
        id="asset-1",
        generic_name="zanubrutinib",
        development_codes=["BGB-3111"],
        brand_names=["Brukinsa"],
        company="BeiGene",
        target="BTK",
        modality="small_molecule",
    )
    assert asset.company == "BeiGene"
    assert asset.brand_names == ["Brukinsa"]
    assert asset.aliases == []  # list fields default empty


def test_asset_minimal_dev_code_only():
    # Early asset known only by a development code: generic_name may be absent.
    asset = Asset(id="asset-2", company="Takeda", development_codes=["TAK-279"])
    assert asset.generic_name is None
    assert asset.development_codes == ["TAK-279"]


def test_asset_anonymous_rejected():
    # No identifier at all (only id + company) -> rejected by the model validator.
    with pytest.raises(ValidationError) as exc_info:
        Asset(id="asset-x", company="Takeda")
    assert (
        "Asset requires at least one identifier: generic_name, "
        "development_codes, brand_names, or aliases" in str(exc_info.value)
    )


def test_asset_whitespace_generic_name_rejected():
    # Whitespace-only generic_name is treated as empty -> does not satisfy the constraint.
    with pytest.raises(ValidationError):
        Asset(id="asset-x", company="Takeda", generic_name="  ")


def test_program_valid_carries_source_ref():
    prog = Program(
        id="prog-1",
        asset_id="asset-1",
        therapeutic_area="oncology",
        indication="chronic lymphocytic leukemia",
        region="US",
        stage="approved",
        as_of_date="2026-05-13",
        source_ref=make_source_ref(),
    )
    assert isinstance(prog.source_ref, SourceRef)
    assert prog.stage == "approved"


def test_trial_valid_optional_nct():
    trial = Trial(
        id="trial-1",
        trial_name="SEQUOIA",
        asset_ids=["asset-1"],
        indication="CLL",
        phase="3",
        primary_endpoint="PFS",
        source_ref=make_source_ref(),
    )
    assert trial.nct_id is None  # nct_id is optional
    assert trial.phase == "3"


def test_regulatory_event_valid_has_no_id():
    evt = RegulatoryEvent(
        asset_id="asset-1",
        agency="FDA",
        region="US",
        action="approval",
        status="granted",
        date="2026-03-01",
        indication="CLL",
        source_ref=make_source_ref(),
    )
    assert evt.action == "approval"
    assert not hasattr(evt, "id")  # RegulatoryEvent has no `id` in the schema


def test_market_metric_valid_has_no_id():
    metric = MarketMetric(
        subject="Novartis",
        metric="revenue",
        value=13283.0,
        unit="USD million",
        currency="USD",
        basis="reported",
        period="Q1 2026",
        geography="Global",
        source_ref=make_source_ref(),
    )
    assert metric.metric == "revenue"
    assert not hasattr(metric, "id")  # MarketMetric has no `id` in the schema


# --------------------------------------------------------------------------- #
# Closed enums reject out-of-vocab values
# --------------------------------------------------------------------------- #
def test_document_bad_doc_type_rejected():
    with pytest.raises(ValidationError):
        Document(id="d", source_company="c", title="t", doc_type="annual_report")


def test_program_bad_stage_and_region_rejected():
    base = dict(
        id="prog-1",
        asset_id="a",
        therapeutic_area="oncology",
        indication="CLL",
        as_of_date="2026",
        source_ref=make_source_ref(),
    )
    with pytest.raises(ValidationError):
        Program(region="US", stage="P5", **base)  # P5 is not a valid stage
    with pytest.raises(ValidationError):
        Program(region="USA", stage="P3", **base)  # USA is not a valid region


def test_trial_bad_phase_rejected():
    with pytest.raises(ValidationError):
        Trial(
            id="t",
            asset_ids=["a"],
            indication="CLL",
            phase="5",  # phase 5 is not in the enum
            source_ref=make_source_ref(),
        )


def test_regulatory_bad_agency_and_action_rejected():
    base = dict(asset_id="a", region="US", indication="CLL", source_ref=make_source_ref())
    with pytest.raises(ValidationError):
        RegulatoryEvent(agency="SFDA", action="approval", **base)  # SFDA invalid
    with pytest.raises(ValidationError):
        RegulatoryEvent(agency="FDA", action="rejected", **base)  # 'rejected' invalid


def test_market_metric_bad_metric_and_basis_rejected():
    base = dict(
        subject="X",
        value=1.0,
        unit="USD million",
        period="Q1 2026",
        geography="US",
        source_ref=make_source_ref(),
    )
    with pytest.raises(ValidationError):
        MarketMetric(metric="ebitda", **base)  # not in metric enum
    with pytest.raises(ValidationError):
        MarketMetric(metric="revenue", basis="adjusted", **base)  # not in basis enum


# --------------------------------------------------------------------------- #
# Open-vocabulary fields accept out-of-vocab strings (multi-TA breadth)
# --------------------------------------------------------------------------- #
def test_open_vocab_accepts_out_of_vocab():
    # therapeutic_area outside the suggested list
    prog = Program(
        id="p",
        asset_id="a",
        therapeutic_area="ophthalmology",  # not in suggested vocab
        indication="geographic atrophy",
        region="EU",
        stage="P2",
        as_of_date="2026",
        source_ref=make_source_ref(),
    )
    assert prog.therapeutic_area == "ophthalmology"

    # target / modality outside the suggested list
    asset = Asset(
        id="a",
        company="NewCo",
        generic_name="novelmab",  # identifier so the Asset is constructible
        target="some-novel-target-XYZ",
        modality="mRNA-LNP",
    )
    assert asset.modality == "mRNA-LNP"
    assert asset.target == "some-novel-target-XYZ"

    # primary_endpoint outside the suggested list
    trial = Trial(
        id="t",
        asset_ids=["a"],
        indication="X",
        phase="2",
        primary_endpoint="time-to-next-treatment",
        source_ref=make_source_ref(),
    )
    assert trial.primary_endpoint == "time-to-next-treatment"


# --------------------------------------------------------------------------- #
# Required fields enforced
# --------------------------------------------------------------------------- #
def test_missing_required_fields_rejected():
    with pytest.raises(ValidationError):  # Document missing title
        Document(id="d", source_company="c", doc_type="other")
    with pytest.raises(ValidationError):  # Asset missing company
        Asset(id="a")
    with pytest.raises(ValidationError):  # SourceRef missing snippet
        SourceRef(document_id="d")


def test_fact_entities_require_source_ref():
    # source_ref is non-negotiable on every fact entity.
    with pytest.raises(ValidationError):
        Program(
            id="p",
            asset_id="a",
            therapeutic_area="oncology",
            indication="CLL",
            region="US",
            stage="P3",
            as_of_date="2026",
        )
    with pytest.raises(ValidationError):
        Trial(id="t", asset_ids=["a"], indication="CLL", phase="3")
    with pytest.raises(ValidationError):
        RegulatoryEvent(asset_id="a", agency="FDA", region="US", action="approval", indication="CLL")
    with pytest.raises(ValidationError):
        MarketMetric(
            subject="X", metric="revenue", value=1.0, unit="USD million",
            period="Q1 2026", geography="US",
        )


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        Document(
            id="d", source_company="c", title="t", doc_type="other", surprise="nope"
        )


# --------------------------------------------------------------------------- #
# Serialization / deserialization round-trips
# --------------------------------------------------------------------------- #
def test_program_round_trip_dict_and_json():
    prog = Program(
        id="prog-1",
        asset_id="asset-1",
        therapeutic_area="oncology",
        indication="CLL",
        region="US",
        stage="approved",
        as_of_date="2026-05-13",
        source_ref=make_source_ref(),
    )

    dumped = prog.model_dump()
    assert dumped["source_ref"]["snippet"].startswith("zanubrutinib")
    assert Program.model_validate(dumped) == prog

    assert Program.model_validate_json(prog.model_dump_json()) == prog
