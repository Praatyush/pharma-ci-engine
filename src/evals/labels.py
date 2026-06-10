"""Golden-label schema + loader — hand-made ground truth the harness scores against.

A golden file is **one JSON per document** under ``src/evals/golden/`` (tracked in
git; ground truth, changed deliberately — never to chase a score). It labels a
*subset* of the document's chunks (the dense, hand-labelable ones) with the facts
a perfect extractor should produce from each.

Design choices baked in here (see ``docs/HANDOFF.md`` Phase 2):

- **Labels are key-agnostic.** Each entity records *every* field a match key OR a
  scored attribute might need; which fields are keys vs attributes is decided later
  in ``matching.py``, not here. That keeps the labels stable if a key is retuned.
- **Assets record ALL surface forms** (``identifiers``: generic name, dev codes,
  brand names, aliases). The same molecule is referenced by different slugs across
  fact types (e.g. ``ianalumab`` vs ``VAY736``), so fact->asset resolution matches a
  fact's ``asset`` against the asset's whole identifier set.
- **Closed-vocabulary fields reuse the schema's ``Literal`` aliases**, so a label
  typo (``stage: "Phase 3"``) fails validation — golden is typed too.
- ``extra="forbid"`` rejects stray/misspelled keys in the hand-written JSON.

The loader validates the file and exposes the labeled chunk indices (the
precision-scoping set: predicted facts are only judged where there are labels).
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

GOLDEN_SCHEMA_VERSION = "1"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoldenAsset(_Base):
    """A molecule. ``identifiers`` lists every observed surface form (>=1)."""

    identifiers: list[str] = Field(..., min_length=1, description="All surface forms: generic name, dev codes, brand names, aliases.")
    modality: str | None = Field(None, description="Scored attribute (open free-text).")
    target: str | None = Field(None, description="Scored attribute (open free-text).")

    @field_validator("identifiers")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not any(s and s.strip() for s in v):
            raise ValueError("identifiers must contain at least one non-empty string")
        return v


class GoldenProgram(_Base):
    """asset x indication x region x stage. Key: (asset, indication, region, stage)."""

    asset: str = Field(..., description="Any one identifier of the asset (resolved via its identifier set).")
    indication: str = Field(..., description="Key (fuzzy-matched, open free-text).")
    region: Region = Field(..., description="Key (exact closed enum).")
    stage: ProgramStage = Field(..., description="Key (exact closed enum).")
    therapeutic_area: str | None = Field(None, description="Scored attribute (open free-text).")
    line_of_therapy: str | None = Field(None, description="Scored attribute.")


class GoldenTrial(_Base):
    """Key: nct_id -> trial_name -> (assets + indication + phase)."""

    indication: str = Field(..., description="Key (fuzzy-matched).")
    phase: TrialPhase = Field(..., description="Key (exact closed enum).")
    trial_name: str | None = Field(None, description="Key when present (normalized).")
    nct_id: str | None = Field(None, description="Strongest key when present (exact).")
    assets: list[str] = Field(default_factory=list, description="Asset identifier(s) studied (combos allowed).")
    primary_endpoint: str | None = Field(None, description="Scored attribute (open free-text).")
    met_primary_endpoint: bool | None = Field(None, description="Scored attribute.")


class GoldenRegulatoryEvent(_Base):
    """Key: (asset, action, indication, region). agency = scored attribute."""

    asset: str = Field(..., description="Any one identifier of the asset.")
    action: RegulatoryAction = Field(..., description="Key (exact closed enum).")
    indication: str = Field(..., description="Key (fuzzy-matched).")
    region: Region = Field(..., description="Key (exact closed enum).")
    agency: Agency = Field(..., description="Scored attribute (still labeled). PMDA==MHLW in scoring.")
    from_progress_row: bool = Field(
        ...,
        description="True if derived from a pipeline progress-table row (co-located with a "
        "Program); False for a standalone prose action. Lets metrics.py report standalone "
        "reg-event recall separately — the hard, headline case.",
    )
    status: RegulatoryStatus | None = Field(None, description="Scored attribute.")
    date: str | None = Field(None, description="Scored attribute.")


class GoldenMarketMetric(_Base):
    """Key: (subject, metric, geography). value/period/currency/basis = attributes."""

    subject: str = Field(..., description="Key: product brand or company name (normalized).")
    metric: MarketMetricType = Field(..., description="Key (exact closed enum).")
    geography: str = Field(..., description="Key (normalized open free-text).")
    value: float = Field(..., description="Scored attribute; compared scale-normalized via unit.")
    unit: str = Field(..., description="Gives the scale (million/billion/...) for value normalization.")
    currency: str | None = Field(None, description="Scored attribute (e.g. 'USD').")
    period: str | None = Field(None, description="Scored attribute; defaults to document reporting_period when absent.")
    basis: MarketMetricBasis | None = Field(None, description="Scored attribute.")


class GoldenChunk(_Base):
    """Ground-truth facts for one labeled chunk (by its original ``chunk_index``)."""

    chunk_index: int = Field(..., ge=0, description="Original 0-based chunk index in the document.")
    line_range: tuple[int, int] | None = Field(None, description="For human reference; mirrors the chunk's provenance.")
    note: str | None = Field(None, description="Optional labeler comment.")
    assets: list[GoldenAsset] = Field(default_factory=list)
    programs: list[GoldenProgram] = Field(default_factory=list)
    trials: list[GoldenTrial] = Field(default_factory=list)
    regulatory_events: list[GoldenRegulatoryEvent] = Field(default_factory=list)
    market_metrics: list[GoldenMarketMetric] = Field(default_factory=list)


class GoldenDocument(_Base):
    """A document's golden labels: header provenance + the labeled chunks."""

    golden_schema_version: str = Field(..., description="Must equal GOLDEN_SCHEMA_VERSION.")
    document_id: str = Field(..., description="Matches the extraction artifact's document_id.")
    source_company: str
    artifact: str = Field(..., description="Filename of the extraction artifact these labels score.")
    reporting_period: str | None = Field(None, description="Document's primary period; the default for MarketMetric.period scoring.")
    as_of_date: str | None = Field(None, description="Document snapshot date (mirrors the extraction run).")
    labeled_chunks: list[GoldenChunk] = Field(..., min_length=1)

    @field_validator("labeled_chunks")
    @classmethod
    def _unique_chunk_indices(cls, v: list[GoldenChunk]) -> list[GoldenChunk]:
        seen = [c.chunk_index for c in v]
        dupes = {i for i in seen if seen.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate chunk_index in labeled_chunks: {sorted(dupes)}")
        return v

    def labeled_chunk_indices(self) -> set[int]:
        """The precision-scoping set: predicted facts are judged only in these chunks."""
        return {c.chunk_index for c in self.labeled_chunks}


def load_golden(path: str | Path) -> GoldenDocument:
    """Load + validate a golden label file.

    Raises ``ValueError`` on an unrecognized ``golden_schema_version`` (don't
    silently misread a future format); Pydantic raises on any field/enum violation.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("golden_schema_version")
    if version != GOLDEN_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported golden_schema_version {version!r} "
            f"(this build reads {GOLDEN_SCHEMA_VERSION!r})."
        )
    return GoldenDocument.model_validate(data)
