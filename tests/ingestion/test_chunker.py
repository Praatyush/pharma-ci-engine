"""Tests for src/ingestion/chunker.py — chunk generation, provenance, splitting."""

import pytest

from src.ingestion import Chunk, ChunkConfig, chunk_document
from src.ingestion.loader import LoadedReport
from src.schema import Document, SourceRef


def _loaded(text: str, doc_id: str = "doc-1") -> LoadedReport:
    """Build a LoadedReport directly from markdown text (no file IO)."""
    lines = text.split("\n")
    doc = Document(id=doc_id, source_company="X", title="T", doc_type="other")
    return LoadedReport(document=doc, text="\n".join(lines), lines=lines)


# --------------------------------------------------------------------------- #
# Chunk generation
# --------------------------------------------------------------------------- #
def test_chunk_generation_and_verbatim_coverage():
    md = "# A\nalpha\n## B\nbeta\n## C\ngamma\n"
    loaded = _loaded(md)
    chunks = chunk_document(loaded, ChunkConfig(chunk_size=1000, overlap=100))

    assert len(chunks) >= 1
    assert all(isinstance(c, Chunk) for c in chunks)
    # chunk_index is sequential from 0
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # every chunk's text is the verbatim slice named by its line_range
    for c in chunks:
        start, end = c.line_range
        assert c.text == "\n".join(loaded.lines[start - 1:end])


def test_small_sections_are_packed():
    md = "# A\nalpha\n## B\nbeta\n## C\ngamma\n"
    loaded = _loaded(md)
    # a generous budget packs every section into a single chunk
    chunks = chunk_document(loaded, ChunkConfig(chunk_size=1000, overlap=100))
    assert len(chunks) == 1
    assert chunks[0].line_range == (1, len(loaded.lines))
    assert chunks[0].section_path == ["A"]  # breadcrumb at the chunk start


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
def test_provenance_and_to_source_ref():
    md = "# Title\nsome content here\n"
    loaded = _loaded(md, doc_id="rep-1")
    chunk = chunk_document(loaded, ChunkConfig(chunk_size=1000, overlap=100))[0]

    assert chunk.document_id == "rep-1"
    assert 1 <= chunk.line_range[0] <= chunk.line_range[1]
    assert chunk.text  # snippet source is non-empty

    ref = chunk.to_source_ref()
    assert isinstance(ref, SourceRef)
    assert ref.document_id == "rep-1"
    assert ref.line_range == chunk.line_range
    assert ref.snippet == chunk.text
    assert ref.section == "Title"  # section_label from the breadcrumb


def test_to_source_ref_truncates_snippet_when_asked():
    loaded = _loaded("# T\n" + ("x" * 500) + "\n")
    chunk = chunk_document(loaded, ChunkConfig(chunk_size=2000, overlap=100))[0]
    ref = chunk.to_source_ref(max_snippet_chars=50)
    assert len(ref.snippet) == 50


def test_breadcrumb_hierarchy_is_nested():
    # a nested section whose body exceeds the budget keeps its full header path
    body = "x" * 60
    md = f"# Top\n## Mid\n### Deep\n{body}\n"
    loaded = _loaded(md)
    chunks = chunk_document(loaded, ChunkConfig(chunk_size=40, overlap=5))
    deep = [c for c in chunks if c.section_path == ["Top", "Mid", "Deep"]]
    assert deep, [c.section_path for c in chunks]


def test_preheader_content_has_empty_section_path():
    md = "intro line\nmore intro\n# First Header\nbody\n"
    loaded = _loaded(md)
    chunks = chunk_document(loaded, ChunkConfig(chunk_size=12, overlap=2))
    # the first chunk covers the pre-header preamble -> empty breadcrumb
    assert chunks[0].section_path == []
    assert chunks[0].to_source_ref().section is None


# --------------------------------------------------------------------------- #
# Oversized-section splitting
# --------------------------------------------------------------------------- #
def test_oversized_section_splits_into_overlapping_windows():
    body = "abcdefghij" * 10  # 100 chars, no internal newlines
    md = f"# Big\n{body}\n"
    loaded = _loaded(md)
    cfg = ChunkConfig(chunk_size=40, overlap=10)
    chunks = chunk_document(loaded, cfg)

    big = [c for c in chunks if c.section_path == ["Big"]]
    assert len(big) > 1  # the section was split into multiple windows
    for c in big:
        assert len(c.text) <= cfg.chunk_size  # windows respect the size cap
    # consecutive windows overlap by exactly `overlap` characters
    assert big[0].text[-cfg.overlap:] == big[1].text[: cfg.overlap]
    # line ranges stay within the document; window text is a verbatim substring
    for c in big:
        start, end = c.line_range
        assert 1 <= start <= end <= len(loaded.lines)
        assert c.text in loaded.text


def test_oversized_window_line_ranges_are_accurate():
    # two long lines under one header; windows should map to the right line numbers
    line2 = "A" * 50
    line3 = "B" * 50
    md = f"# H\n{line2}\n{line3}\n"
    loaded = _loaded(md)
    chunks = chunk_document(loaded, ChunkConfig(chunk_size=30, overlap=5))
    # at least one window should sit entirely within line 2, and one within line 3
    assert any(c.line_range == (2, 2) for c in chunks), [c.line_range for c in chunks]
    assert any(c.line_range == (3, 3) for c in chunks), [c.line_range for c in chunks]


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def test_chunk_config_validation():
    with pytest.raises(ValueError):
        ChunkConfig(chunk_size=100, overlap=100)  # overlap must be < chunk_size
    with pytest.raises(ValueError):
        ChunkConfig(chunk_size=0, overlap=0)       # chunk_size must be > 0
    with pytest.raises(ValueError):
        ChunkConfig(chunk_size=100, overlap=-1)    # overlap must be >= 0
