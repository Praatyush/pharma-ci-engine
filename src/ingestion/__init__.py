"""ingestion — load markdown reports (data/reports/) and section-aware chunk them.

v1 is markdown-only (PDF ingestion deferred — see ARCHITECTURE.md). ``load_report``
produces a ``LoadedReport`` (schema ``Document`` + cleaned text/lines);
``chunk_document`` splits it into ``Chunk``s carrying provenance sufficient to
build a ``schema.SourceRef``. No LLM is called here.
"""

from .chunker import Chunk, ChunkConfig, chunk_document
from .loader import LoadedReport, load_report

__all__ = [
    "Chunk",
    "ChunkConfig",
    "chunk_document",
    "LoadedReport",
    "load_report",
]
