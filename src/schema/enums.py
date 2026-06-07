"""Closed vocabularies for the domain schema (ARCHITECTURE.md -> "Closed enums").

These are the small, stable vocabularies kept strict: extraction must emit
exactly one of the listed values, and evals score them by exact match.

Modeled as ``Literal`` aliases rather than ``Enum`` because (a) several values
are not valid Python identifiers (e.g. ``"1/2"``, ``"P1/2"``) and would need
ugly aliasing as Enum members, and (b) ``Literal`` validates against — and
serializes to — the bare string value, which is exactly what structured-output
extraction and exact-match evals expect.

Open vocabularies (therapeutic_area, indication, target, modality,
primary_endpoint) are deliberately NOT here: they are plain ``str`` on the
models, carrying only a *suggested* vocab in their field descriptions.
"""

from typing import Literal

# Document.doc_type
DocType = Literal["pipeline_table", "financial_report", "press_release", "other"]

# region — shared by Program, Trial, RegulatoryEvent
Region = Literal["US", "EU", "JP", "CN", "Global", "other"]

# Program.stage — the asset's lifecycle in an indication/region.
# A different axis from Trial.phase — do not collapse them.
ProgramStage = Literal[
    "preclinical",
    "P1",
    "P1/2",
    "P2",
    "P2a",
    "P2b",
    "P3",
    "filed",
    "approved",
    "discontinued",
]

# Trial.phase — a specific trial's phase. A different axis from Program.stage.
TrialPhase = Literal["1", "1/2", "2", "2a", "2b", "3", "4"]

# RegulatoryEvent.agency
Agency = Literal["FDA", "EMA", "PMDA", "NMPA", "MHLW", "other"]

# RegulatoryEvent.action
RegulatoryAction = Literal[
    "filed",
    "approval",
    "CRL",
    "priority_review",
    "breakthrough",
    "fast_track",
    "orphan",
    "PRIME",
    "CHMP_opinion",
    "application_withdrawal",
    "product_withdrawal",
    "other",
]

# RegulatoryEvent.status (optional)
RegulatoryStatus = Literal["granted", "pending", "denied"]

# MarketMetric.metric
MarketMetricType = Literal[
    "revenue",
    "growth_rate",
    "market_share",
    "patient_count",
    "country_count",
]

# MarketMetric.basis (optional)
MarketMetricBasis = Literal["reported", "constant_currency"]
