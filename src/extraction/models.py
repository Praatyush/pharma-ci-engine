"""Extraction-view Pydantic models — the ``response_schema`` targets for Gemini.

These mirror the schema fact entities but deliberately OMIT ``source_ref`` and our
internal ``id``s: those are code-assigned from the originating chunk, never
model-generated, so grounding can't be hallucinated. Closed-vocabulary fields
reuse the schema's ``Literal`` aliases so Gemini enforces them; open-vocabulary
fields are plain ``str``. Every item carries ``evidence`` — a verbatim quote used
to verify/narrow the ``SourceRef`` snippet downstream.

No ``google.genai`` import here; this module only describes shapes.
"""

from pydantic import BaseModel, Field

from src.schema.enums import (
    Agency,
    MarketMetricBasis,
    MarketMetricType,
    ProgramStage,
    Region,
    RegulatoryAction,
    RegulatoryStatus,
    TrialPhase,
)


class ExtractedAsset(BaseModel):
    generic_name: str | None = None
    development_codes: list[str] = Field(default_factory=list)
    brand_names: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    company: str | None = None
    originator_company: str | None = None
    target: str | None = None
    mechanism_of_action: str | None = None
    modality: str | None = None
    route: str | None = None
    evidence: str


class ExtractedProgram(BaseModel):
    asset_ref: str
    therapeutic_area: str
    indication: str
    region: Region
    stage: ProgramStage
    line_of_therapy: str | None = None
    status_reason: str | None = None
    formulation: str | None = None
    as_of_date: str | None = None
    evidence: str


class ExtractedTrial(BaseModel):
    asset_refs: list[str] = Field(default_factory=list)
    indication: str
    phase: TrialPhase
    trial_name: str | None = None
    nct_id: str | None = None
    comparator: str | None = None
    primary_endpoint: str | None = None
    met_primary_endpoint: bool | None = None
    statistical_significance: str | None = None
    endpoint_result: str | None = None
    readout_date: str | None = None
    region: Region | None = None
    evidence: str


class ExtractedRegulatoryEvent(BaseModel):
    asset_ref: str
    agency: Agency
    region: Region
    action: RegulatoryAction
    indication: str
    status: RegulatoryStatus | None = None
    date: str | None = None
    evidence: str


class ExtractedMarketMetric(BaseModel):
    subject_ref: str
    metric: MarketMetricType
    value: float
    unit: str
    period: str
    geography: str
    currency: str | None = None
    basis: MarketMetricBasis | None = None
    evidence: str


class ChunkExtraction(BaseModel):
    """The structured payload Gemini returns for one chunk."""

    assets: list[ExtractedAsset] = Field(default_factory=list)
    programs: list[ExtractedProgram] = Field(default_factory=list)
    trials: list[ExtractedTrial] = Field(default_factory=list)
    regulatory_events: list[ExtractedRegulatoryEvent] = Field(default_factory=list)
    market_metrics: list[ExtractedMarketMetric] = Field(default_factory=list)
