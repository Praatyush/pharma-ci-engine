"""Persist an :class:`ExtractionResult` to / from JSON on disk.

The one-time Flash-Lite extraction is expensive (free-tier RPD) and was, in the
prior run, lost because it lived only in memory / ``/tmp``. This module makes the
extraction output a **durable, reproducible artifact**: the fixed input the
Phase-2 eval harness scores against, so re-running the harness never re-burns
quota.

The on-disk shape is::

    {
      "schema_version": "1",
      "meta":   {...run provenance: model, prompt hash, git sha, timestamp...},
      "counts": {assets, programs, trials, regulatory_events, market_metrics},
      "result": {assets: [...], programs: [...], ...}   # schema models, JSON form
    }

``result`` holds the full schema entities (each fact with its ``source_ref``), so
the artifact round-trips losslessly back into :class:`ExtractionResult`. No
``google.genai`` import here — this module only serializes shapes.
"""

import json
from pathlib import Path
from typing import Any

from src.schema import (
    Asset,
    MarketMetric,
    Program,
    RegulatoryEvent,
    Trial,
)

from .extractor import ExtractionResult

SCHEMA_VERSION = "1"

# field name on ExtractionResult -> the schema model it deserializes back into.
_ENTITY_TYPES: dict[str, type] = {
    "assets": Asset,
    "programs": Program,
    "trials": Trial,
    "regulatory_events": RegulatoryEvent,
    "market_metrics": MarketMetric,
}


def count_by_type(result: ExtractionResult) -> dict[str, int]:
    """Per-entity-type counts — used in the run summary and the artifact header."""
    return {name: len(getattr(result, name)) for name in _ENTITY_TYPES}


def result_to_dict(result: ExtractionResult) -> dict[str, list[dict[str, Any]]]:
    """Serialize each entity list with Pydantic ``model_dump(mode="json")``.

    ``mode="json"`` renders nested ``SourceRef`` and the ``line_range`` tuple in
    JSON-native forms so the file is plain JSON.
    """
    return {
        name: [obj.model_dump(mode="json") for obj in getattr(result, name)]
        for name in _ENTITY_TYPES
    }


def result_from_dict(data: dict[str, Any]) -> ExtractionResult:
    """Rebuild an :class:`ExtractionResult` from the ``result`` block of an artifact."""
    return ExtractionResult(
        **{
            name: [model.model_validate(item) for item in data.get(name, [])]
            for name, model in _ENTITY_TYPES.items()
        }
    )


def save_extraction(
    path: str | Path,
    result: ExtractionResult,
    *,
    meta: dict[str, Any],
) -> Path:
    """Write ``result`` (+ provenance ``meta``) to ``path`` as JSON; returns the path.

    Creates parent directories. ``meta`` is caller-supplied run provenance
    (model, prompt hash, git sha, timestamp, chunk config, ...) so a saved artifact
    is self-describing and diffable across runs.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "meta": meta,
        "counts": count_by_type(result),
        "result": result_to_dict(result),
    }
    path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_extraction(path: str | Path) -> tuple[dict[str, Any], ExtractionResult]:
    """Load an artifact written by :func:`save_extraction` -> ``(meta, result)``.

    Raises ``ValueError`` on an unrecognized ``schema_version`` rather than
    silently misreading a future format.
    """
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    version = artifact.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported extraction artifact schema_version {version!r} "
            f"(this build reads {SCHEMA_VERSION!r})."
        )
    return artifact.get("meta", {}), result_from_dict(artifact.get("result", {}))
