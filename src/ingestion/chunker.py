"""Section-aware chunking for markdown reports.

Strategy (``docs/ARCHITECTURE.md`` -> ingestion):

1. Parse the document into sections by ATX headers (``#``..``######``), tracking
   a header breadcrumb (the nested header path) for provenance.
2. Pack consecutive sections into one chunk up to ``chunk_size`` characters,
   breaking at section boundaries — so the many tiny sections produced by
   table-derived markdown coalesce instead of becoming one chunk each.
3. Split an oversized *single* section (> ``chunk_size``) into overlapping
   character windows.

Each :class:`Chunk` carries provenance sufficient to build a ``schema.SourceRef``:
``document_id``, the section/header path, a 1-based inclusive ``line_range``, and
the verbatim ``text`` (which doubles as the citation snippet). No LLM is called
here — extraction consumes these chunks downstream.
"""

import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from src.schema import SourceRef
from .loader import LoadedReport

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class ChunkConfig:
    """Chunking parameters, in characters. Both are configurable."""

    chunk_size: int = 1500
    overlap: int = 200

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if self.overlap < 0:
            raise ValueError("overlap must be >= 0")
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be < chunk_size")


class Chunk(BaseModel):
    """One chunk of a document plus the provenance needed to cite it."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(..., description="id of the source Document.")
    chunk_index: int = Field(..., description="0-based position of this chunk within the document.")
    section_path: list[str] = Field(
        default_factory=list,
        description="Header breadcrumb active at the chunk's start, outermost first. Empty for pre-header content.",
    )
    line_range: tuple[int, int] = Field(
        ..., description="(start_line, end_line), 1-based inclusive, into the document's canonical lines."
    )
    text: str = Field(..., description="Verbatim chunk text — also serves as the citation snippet.")

    @property
    def section_label(self) -> str | None:
        """The breadcrumb joined for ``SourceRef.section`` (None if pre-header)."""
        return " > ".join(self.section_path) if self.section_path else None

    def to_source_ref(self, max_snippet_chars: int | None = None) -> SourceRef:
        """Build a ``schema.SourceRef`` citing this chunk."""
        snippet = self.text if max_snippet_chars is None else self.text[:max_snippet_chars]
        return SourceRef(
            document_id=self.document_id,
            section=self.section_label,
            line_range=self.line_range,
            snippet=snippet,
        )


@dataclass(frozen=True)
class _Section:
    """An internal header-delimited span: lines ``start_line..end_line`` inclusive."""

    path: tuple[str, ...]
    start_line: int
    end_line: int


def _range_text(lines: list[str], start: int, end: int) -> str:
    """Verbatim text of 1-based inclusive line range ``start..end``."""
    return "\n".join(lines[start - 1:end])


def _parse_sections(lines: list[str]) -> list[_Section]:
    """Split lines into header-delimited sections, tracking the nested header path.

    A section runs from a header line (inclusive) to the line before the next
    header of any level. Content before the first header becomes a section with
    an empty path.
    """
    sections: list[_Section] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    cur_path: tuple[str, ...] = ()
    cur_start = 1

    for i, line in enumerate(lines, start=1):
        match = _HEADER_RE.match(line.strip())
        if not match:
            continue
        if i - 1 >= cur_start:  # close the span preceding this header
            sections.append(_Section(cur_path, cur_start, i - 1))
        level = len(match.group(1))
        title = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        cur_path = tuple(t for _, t in stack)
        cur_start = i

    if len(lines) >= cur_start:  # close the final span
        sections.append(_Section(cur_path, cur_start, len(lines)))
    return sections


def _window_section(
    lines: list[str], section: _Section, config: ChunkConfig
) -> list[tuple[tuple[int, int], str]]:
    """Split an oversized section into overlapping char windows with line ranges."""
    text = _range_text(lines, section.start_line, section.end_line)

    # Char offset at which each of the section's lines begins (for offset->line).
    offsets: list[int] = []
    off = 0
    for k in range(section.end_line - section.start_line + 1):
        offsets.append(off)
        off += len(lines[section.start_line - 1 + k]) + 1  # +1 for the joining "\n"

    def offset_to_line(pos: int) -> int:
        lo, hi, ans = 0, len(offsets) - 1, 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if offsets[mid] <= pos:
                ans, lo = mid, mid + 1
            else:
                hi = mid - 1
        return section.start_line + ans

    stride = config.chunk_size - config.overlap
    windows: list[tuple[tuple[int, int], str]] = []
    pos, n = 0, len(text)
    while pos < n:
        end = min(pos + config.chunk_size, n)
        windows.append(((offset_to_line(pos), offset_to_line(end - 1)), text[pos:end]))
        if end == n:
            break
        pos += stride
    return windows


def chunk_document(loaded: LoadedReport, config: ChunkConfig = ChunkConfig()) -> list[Chunk]:
    """Chunk a :class:`LoadedReport` section-aware, packing small sections and
    char-windowing oversized ones. Returns chunks in document order."""
    lines = loaded.lines
    document_id = loaded.document.id
    chunks: list[Chunk] = []

    # Packing buffer for consecutive small sections (contiguous line spans).
    buf_start: int | None = None
    buf_end: int | None = None
    buf_path: tuple[str, ...] = ()

    def flush() -> None:
        nonlocal buf_start, buf_end, buf_path
        if buf_start is None:
            return
        chunks.append(
            Chunk(
                document_id=document_id,
                chunk_index=len(chunks),
                section_path=list(buf_path),
                line_range=(buf_start, buf_end),
                text=_range_text(lines, buf_start, buf_end),
            )
        )
        buf_start = buf_end = None
        buf_path = ()

    for section in _parse_sections(lines):
        section_text = _range_text(lines, section.start_line, section.end_line)

        if len(section_text) > config.chunk_size:  # oversized: window it alone
            flush()
            for line_range, text in _window_section(lines, section, config):
                chunks.append(
                    Chunk(
                        document_id=document_id,
                        chunk_index=len(chunks),
                        section_path=list(section.path),
                        line_range=line_range,
                        text=text,
                    )
                )
            continue

        if buf_start is None:  # start a new buffer
            buf_start, buf_end, buf_path = section.start_line, section.end_line, section.path
        elif len(_range_text(lines, buf_start, section.end_line)) > config.chunk_size:
            flush()  # adding this section would overflow -> flush, then start fresh
            buf_start, buf_end, buf_path = section.start_line, section.end_line, section.path
        else:
            buf_end = section.end_line  # extend; keep the breadcrumb at buffer start

    flush()
    return chunks
