"""The pharma-CI domain schema — 7 Pydantic v2 entities.

ARCHITECTURE.md -> "Domain schema". Two provenance types (``Document``,
``SourceRef``), one noun (``Asset``), and four dated fact entities (``Program``,
``Trial``, ``RegulatoryEvent``, ``MarketMetric``) that each carry a
``SourceRef`` — that ``source_ref`` is non-negotiable; it is what makes citation
and the faithfulness eval possible.

Closed vocabularies are imported from ``enums`` (Literal aliases). Open
vocabularies (``therapeutic_area``, ``indication``, ``target``, ``modality``,
``primary_endpoint``) are plain ``str`` with a *suggested* vocab in the field
description; out-of-vocab values pass through verbatim — this is the deliberate
mechanism for multi-TA breadth without sacrificing per-field reliability.

Temporal fields (dates / periods) are typed as ``str``, not ``datetime.date``,
on purpose: pharma sources state them in mixed, frequently partial forms
("Q1 2026", "1H 2026", "as of May 13, 2026", "expected 2027"), and forcing
strict date parsing would hurt extraction reliability — the schema's first
design priority. Store ISO-8601 where the source gives a full date; store the
source's verbatim expression otherwise.
"""

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    Agency,
    DocType,
    MarketMetricBasis,
    MarketMetricType,
    ProgramStage,
    Region,
    RegulatoryAction,
    RegulatoryStatus,
    TrialPhase,
)


class _Base(BaseModel):
    """Shared config — treat the schema as a strict contract.

    ``extra="forbid"`` rejects unknown / hallucinated fields, which keeps
    structured-output extraction honest and makes the eval comparison clean.
    """

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
class Document(_Base):
    """The source artifact a fact was extracted from."""

    id: str = Field(..., description="Stable internal identifier for this document.")
    source_company: str = Field(
        ..., description="Company that published the document, e.g. 'Novartis', 'Takeda'."
    )
    title: str = Field(..., description="Document title as published.")
    doc_type: DocType = Field(
        ...,
        description="Closed enum: pipeline_table | financial_report | press_release | other.",
    )
    publication_date: str | None = Field(
        None,
        description="Date the document was published. ISO-8601 if known, else verbatim (e.g. 'Q1 2026').",
    )
    period_covered: str | None = Field(
        None,
        description="Reporting period the document covers, e.g. 'Q1 2026', 'FY2025'. None for point-in-time snapshots like a pipeline table.",
    )
    url: str | None = Field(
        None,
        description="Source URL if any. Typically None in v1 — the corpus is local markdown in data/reports/.",
    )
    language: str | None = Field(
        None, description="ISO 639-1 language code of the document, e.g. 'en'."
    )


class SourceRef(_Base):
    """A citation back into a ``Document`` — attached to every fact entity.

    The locator is flexible (page / section / line_range) because markdown and
    tables have no fixed pages; at least one locator field should be populated.
    """

    document_id: str = Field(..., description="id of the Document this fact came from.")
    page: int | None = Field(
        None, description="Page number when the source has fixed pages. Usually None for markdown."
    )
    section: str | None = Field(
        None,
        description="Section / heading the snippet was found under, e.g. 'Oncology pipeline'.",
    )
    line_range: tuple[int, int] | None = Field(
        None,
        description="(start_line, end_line) of the snippet within the markdown document, 1-based inclusive.",
    )
    snippet: str = Field(
        ..., description="Verbatim source text supporting the fact — the citation evidence."
    )
    as_of_date: str | None = Field(
        None,
        description="Snapshot date the SOURCE states, e.g. 'as of May 13, 2026' — a property of the document. None if the source states none. Distinct from Program.as_of_date.",
    )


# --------------------------------------------------------------------------- #
# Noun
# --------------------------------------------------------------------------- #
class Asset(_Base):
    """A drug as a noun — one molecule.

    ``indication`` is intentionally NOT here: one asset is pursued across many
    indications; that lives on ``Program``. One asset -> many programs.
    """

    id: str = Field(..., description="Stable internal identifier for this asset (molecule).")
    generic_name: str | None = Field(
        None,
        description="International nonproprietary name, e.g. 'zanubrutinib'. None for early assets known only by a development code.",
    )
    development_codes: list[str] = Field(
        default_factory=list,
        description="Development codes as observed, e.g. ['TAK-279', 'NDI-034858'].",
    )
    brand_names: list[str] = Field(
        default_factory=list, description="Marketed brand name(s) as observed, e.g. ['Calquence']."
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Other names/aliases as observed. Stored as-is; cross-document alias resolution is deferred.",
    )
    company: str = Field(
        ..., description="Current owner/developer company (plain string; companies are not an entity)."
    )
    originator_company: str | None = Field(
        None, description="Originating company if different from the current owner."
    )
    target: str | None = Field(
        None,
        description="Open free-text. Molecular target, e.g. 'Claudin 18.2', 'TYK2', 'BCR-ABL', 'FRalpha'. None if undisclosed.",
    )
    mechanism_of_action: str | None = Field(
        None, description="Mechanism of action, free text. None if undisclosed."
    )
    modality: str | None = Field(
        None,
        description="Open free-text. Suggested: small_molecule, mAb, ADC, bispecific, radioligand, gene_therapy, cell_therapy, siRNA/RNAi, peptide, plasma_derived, vaccine. Out-of-vocab passes through verbatim.",
    )
    route: str | None = Field(
        None, description="Route of administration, e.g. 'oral', 'IV', 'subcutaneous'."
    )


# --------------------------------------------------------------------------- #
# Fact entities (each carries a SourceRef)
# --------------------------------------------------------------------------- #
class Program(_Base):
    """A dated development fact: asset x indication x region x stage.

    The native shape of a pipeline-table row. ``stage`` (asset lifecycle) and
    ``Trial.phase`` are different axes — do not collapse them.
    """

    id: str = Field(..., description="Stable internal identifier for this program fact.")
    asset_id: str = Field(..., description="id of the Asset this program develops.")
    therapeutic_area: str = Field(
        ...,
        description="Open free-text. Suggested: oncology, immunology, neuroscience, gastroenterology, rare_disease, vaccines, cardiometabolic. Out-of-vocab passes through verbatim.",
    )
    indication: str = Field(
        ...,
        description="Open free-text indication being pursued, e.g. 'gastric cancer', 'ulcerative colitis'.",
    )
    line_of_therapy: str | None = Field(
        None, description="Line of therapy if stated, e.g. '1L', '2L+', 'maintenance'."
    )
    region: Region = Field(..., description="Closed enum: US | EU | JP | CN | Global | other.")
    stage: ProgramStage = Field(
        ...,
        description="Closed enum: preclinical | P1 | P1/2 | P2 | P2a | P2b | P3 | filed | approved | discontinued. The asset's lifecycle stage in this indication/region.",
    )
    status_reason: str | None = Field(
        None, description="Reason for the current status, e.g. why a program was discontinued."
    )
    formulation: str | None = Field(
        None, description="Formulation if relevant, e.g. 'subcutaneous', 'extended-release'."
    )
    as_of_date: str = Field(
        ...,
        description="Date this pipeline FACT is true as of — a property of the fact. Usually coincides with SourceRef.as_of_date but can differ. ISO-8601 if known, else verbatim.",
    )
    source_ref: SourceRef = Field(
        ..., description="Citation back to the source document. Required on every fact entity."
    )


class Trial(_Base):
    """A clinical trial fact."""

    id: str = Field(..., description="Stable internal identifier for this trial.")
    trial_name: str | None = Field(
        None, description="Trial name/acronym as observed, e.g. 'SEQUOIA', 'CheckMate-901'."
    )
    nct_id: str | None = Field(
        None,
        description="ClinicalTrials.gov identifier, e.g. 'NCT01234567'. Optional — corpus trials are often named by acronym, not NCT.",
    )
    asset_ids: list[str] = Field(
        default_factory=list,
        description="ids of the Asset(s) studied. May list multiple for combinations; combination semantics are not modeled in v1.",
    )
    indication: str = Field(..., description="Open free-text indication studied.")
    phase: TrialPhase = Field(
        ...,
        description="Closed enum: 1 | 1/2 | 2 | 2a | 2b | 3 | 4. A specific trial's phase (distinct from Program.stage).",
    )
    comparator: str | None = Field(
        None,
        description="Comparator arm, e.g. 'placebo', 'standard of care', or a named regimen.",
    )
    primary_endpoint: str | None = Field(
        None,
        description="Open free-text. Suggested: PFS, OS, ORR, DFS, DOR, EFS, pCR, PASI, DLQI, HbA1c, EDSS, immunogenicity. Out-of-vocab passes through verbatim. None if not stated.",
    )
    met_primary_endpoint: bool | None = Field(
        None,
        description="Whether the trial met its primary endpoint. None if not yet read out / not stated.",
    )
    statistical_significance: str | None = Field(
        None, description="Statistical significance as reported, e.g. 'p<0.001', 'HR 0.68'."
    )
    endpoint_result: str | None = Field(
        None,
        description="Result on the primary endpoint as reported. None for ongoing trials with no readout.",
    )
    readout_date: str | None = Field(
        None,
        description="When results read out / are expected, e.g. '2H 2026'. ISO-8601 if known, else verbatim.",
    )
    region: Region | None = Field(
        None, description="Closed enum if stated: US | EU | JP | CN | Global | other."
    )
    source_ref: SourceRef = Field(
        ..., description="Citation back to the source document. Required on every fact entity."
    )


class RegulatoryEvent(_Base):
    """A regulatory action on an asset. No internal ``id`` (per the schema)."""

    asset_id: str = Field(..., description="id of the Asset the action concerns.")
    agency: Agency = Field(..., description="Closed enum: FDA | EMA | PMDA | NMPA | MHLW | other.")
    region: Region = Field(..., description="Closed enum: US | EU | JP | CN | Global | other.")
    action: RegulatoryAction = Field(
        ...,
        description="Closed enum: filed | approval | CRL | priority_review | breakthrough | fast_track | orphan | PRIME | CHMP_opinion | application_withdrawal | product_withdrawal | other.",
    )
    status: RegulatoryStatus | None = Field(
        None, description="Closed enum if stated: granted | pending | denied."
    )
    date: str | None = Field(
        None,
        description="Date of the event — a property of the event. ISO-8601 if known, else verbatim (e.g. 'expected 2026'). None for planned/pending events with no stated date.",
    )
    indication: str = Field(..., description="Open free-text indication the action concerns.")
    source_ref: SourceRef = Field(
        ..., description="Citation back to the source document. Required on every fact entity."
    )


class MarketMetric(_Base):
    """A market / financial metric fact. No internal ``id`` (per the schema)."""

    subject: str = Field(
        ...,
        description="What the metric is about: an Asset id OR a company name (plain-string union, per schema).",
    )
    metric: MarketMetricType = Field(
        ...,
        description="Closed enum: revenue | growth_rate | market_share | patient_count | country_count.",
    )
    value: float = Field(
        ..., description="Numeric value of the metric. Qualifiers live in unit / currency / basis."
    )
    unit: str = Field(
        ..., description="Unit of the value, e.g. 'USD million', '%', 'patients', 'countries'."
    )
    currency: str | None = Field(
        None, description="Currency code if monetary, e.g. 'USD', 'EUR'."
    )
    basis: MarketMetricBasis | None = Field(
        None, description="Closed enum if stated: reported | constant_currency."
    )
    period: str = Field(
        ..., description="Period the metric covers, e.g. 'Q1 2026', 'FY2025'."
    )
    geography: str = Field(
        ..., description="Geography the metric covers, e.g. 'US', 'Global', 'ex-US'."
    )
    source_ref: SourceRef = Field(
        ..., description="Citation back to the source document. Required on every fact entity."
    )
