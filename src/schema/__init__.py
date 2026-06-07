"""schema — the pharma-CI domain model (Pydantic v2).

Seven entities (ARCHITECTURE.md -> "Domain schema"):
  provenance: Document, SourceRef
  noun:       Asset
  facts:      Program, Trial, RegulatoryEvent, MarketMetric  (each carries a SourceRef)

Closed vocabularies live in ``enums`` as Literal aliases; open vocabularies
(therapeutic_area, indication, target, modality, primary_endpoint) are plain str.
"""

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
from .models import (
    Asset,
    Document,
    MarketMetric,
    Program,
    RegulatoryEvent,
    SourceRef,
    Trial,
)

__all__ = [
    # enums (closed vocabularies)
    "Agency",
    "DocType",
    "MarketMetricBasis",
    "MarketMetricType",
    "ProgramStage",
    "Region",
    "RegulatoryAction",
    "RegulatoryStatus",
    "TrialPhase",
    # models
    "Asset",
    "Document",
    "MarketMetric",
    "Program",
    "RegulatoryEvent",
    "SourceRef",
    "Trial",
]
