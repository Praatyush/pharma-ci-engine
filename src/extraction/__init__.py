"""extraction — Gemini structured-output extraction from chunks into schema objects.

Per-chunk extraction (ARCHITECTURE.md): each ``Chunk`` is sent to Gemini with a
``response_schema``-bound payload, then mapped onto the schema fact entities with a
``SourceRef`` grounded on the chunk's ``line_range`` + verbatim ``snippet``.

``gemini_client`` is the only module here that imports ``google.genai``. The public
entry points (``extract_chunk`` / ``extract_document``) and the payload models do
not.
"""

from .extractor import (
    EXTRACTION_SYSTEM_PROMPT,
    ExtractionResult,
    extract_chunk,
    extract_document,
)
from .models import ChunkExtraction
from .persistence import (
    count_by_type,
    load_extraction,
    result_from_dict,
    result_to_dict,
    save_extraction,
)

__all__ = [
    "EXTRACTION_SYSTEM_PROMPT",
    "ExtractionResult",
    "extract_chunk",
    "extract_document",
    "ChunkExtraction",
    "count_by_type",
    "load_extraction",
    "result_from_dict",
    "result_to_dict",
    "save_extraction",
]
