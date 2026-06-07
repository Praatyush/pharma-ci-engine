"""Tests for src/ingestion/loader.py — markdown loading + Document creation."""

from pathlib import Path

from src.ingestion import LoadedReport, load_report
from src.schema import Document


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_creates_document(tmp_path):
    path = _write(tmp_path, "acme_q1_report_en.md", "# Quarterly Update\n\nSome body text.\n")
    loaded = load_report(path, source_company="Acme", doc_type="financial_report")

    assert isinstance(loaded, LoadedReport)
    doc = loaded.document
    assert isinstance(doc, Document)
    assert doc.id == "acme_q1_report_en"          # id from filename stem
    assert doc.source_company == "Acme"
    assert doc.doc_type == "financial_report"
    assert doc.title == "Quarterly Update"        # derived from the first header
    assert doc.language == "en"                    # inferred from the _en suffix
    assert "Some body text." in loaded.text


def test_cleaning_normalizes_newlines_and_strips_bom_and_trailing_ws(tmp_path):
    path = _write(tmp_path, "doc_en.md", "﻿# T\r\n\r\nline with trailing   \r\n")
    loaded = load_report(path, source_company="X", doc_type="other")

    assert "\r" not in loaded.text                 # CRLF normalized to LF
    assert loaded.lines[0] == "# T"                # BOM stripped from first line
    assert "line with trailing" in loaded.text
    assert "trailing   " not in loaded.text        # per-line trailing ws stripped


def test_title_and_language_overrides(tmp_path):
    path = _write(tmp_path, "report.md", "plain first line\nmore\n")
    loaded = load_report(
        path, source_company="X", doc_type="other", title="Explicit Title", language="de"
    )
    assert loaded.document.title == "Explicit Title"
    assert loaded.document.language == "de"


def test_title_defaults_to_first_nonempty_line_when_no_header(tmp_path):
    path = _write(tmp_path, "report.md", "\n\nFirst real line\nsecond\n")
    loaded = load_report(path, source_company="X", doc_type="other")
    assert loaded.document.title == "First real line"
    assert loaded.document.language is None         # no _xx filename suffix


def test_title_skips_noise_subheaders_and_uses_first_nonempty_line(tmp_path):
    # table-derived markdown: only `##` (noise) headers -> use first real line
    path = _write(tmp_path, "pipe_en.md", "\n\nReal Title Line\n## 5\n## Oncology\nbody\n")
    loaded = load_report(path, source_company="X", doc_type="other")
    assert loaded.document.title == "Real Title Line"


def test_title_strips_hashes_when_first_nonempty_line_is_a_header(tmp_path):
    # Novartis-style: no H1; first non-empty line is itself a `##` header
    path = _write(tmp_path, "q1-report.md", "\n\n## Novartis First Quarter 2026\n## Sub\nbody\n")
    loaded = load_report(path, source_company="Novartis", doc_type="financial_report")
    assert loaded.document.title == "Novartis First Quarter 2026"


def test_language_inferred_from_hyphen_suffix(tmp_path):
    path = _write(tmp_path, "q1-2026-interim-financial-report-en.md", "Title\nbody\n")
    loaded = load_report(path, source_company="X", doc_type="other")
    assert loaded.document.language == "en"


def test_lines_are_one_based_addressable(tmp_path):
    path = _write(tmp_path, "doc_en.md", "alpha\nbeta\ngamma\n")
    loaded = load_report(path, source_company="X", doc_type="other")
    # lines[i-1] is line i; text is the lines re-joined
    assert loaded.lines[0] == "alpha"
    assert loaded.lines[2] == "gamma"
    assert loaded.text == "\n".join(loaded.lines)
