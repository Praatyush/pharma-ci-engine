"""Markdown loading + light cleaning for the v1 corpus (``data/reports/``).

v1 is markdown-only (PDF ingestion is deferred — see ``docs/ARCHITECTURE.md``).
This module reads a markdown report from disk, applies minimal, line-stable
normalization, and returns a :class:`LoadedReport`: the schema ``Document``
(metadata) bundled with the cleaned text + line list the chunker needs. The
``Document`` schema has no content field on purpose, so the text travels
alongside it.
"""

from dataclasses import dataclass
from pathlib import Path

from src.schema import Document
from src.schema.enums import DocType

_BOM = "﻿"


@dataclass(frozen=True)
class LoadedReport:
    """A loaded markdown report: schema ``Document`` + its cleaned content.

    ``lines`` are the canonical, 1-based-addressable lines (``lines[i - 1]`` is
    line ``i``); ``text`` is those lines re-joined with ``"\\n"``. Every
    provenance ``line_range`` the chunker emits indexes into ``lines``.
    """

    document: Document
    text: str
    lines: list[str]


def _normalize(raw: str) -> list[str]:
    """Strip a BOM, normalize newlines, and rstrip each line. Line-stable."""
    if raw.startswith(_BOM):
        raw = raw[len(_BOM):]
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    return [line.rstrip() for line in raw.split("\n")]


def _derive_title(lines: list[str]) -> str:
    """First level-1 ``#`` header, else the first non-empty line, else a placeholder.

    Prefers an H1 because sub-headers (``##``+) in table-derived markdown are
    often noise (e.g. a stray ``## 5``). Callers can pass ``title`` explicitly
    when the source has no reliable title line.
    """
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):  # level-1 ATX header only
            return stripped[2:].strip()
    for line in lines:
        stripped = line.strip()
        if stripped:
            # if the fallback line is itself an ATX header, drop the leading #'s + spaces
            return stripped.lstrip("#").strip() if stripped.startswith("#") else stripped
    return "(untitled)"


def _infer_language(stem: str) -> str | None:
    """Infer language from a trailing ``_xx`` or ``-xx`` filename token (-> 'en')."""
    sep = max(stem.rfind("_"), stem.rfind("-"))
    if sep == -1:
        return None
    token = stem[sep + 1:]
    if len(token) == 2 and token.isalpha():
        return token.lower()
    return None


def load_report(
    path: str | Path,
    *,
    source_company: str,
    doc_type: DocType,
    title: str | None = None,
    publication_date: str | None = None,
    period_covered: str | None = None,
    url: str | None = None,
    language: str | None = None,
) -> LoadedReport:
    """Load a markdown report into a :class:`LoadedReport`.

    ``source_company`` and ``doc_type`` are required: they are not reliably
    inferable from the file. ``id`` is the filename stem; ``title`` defaults to
    the first header / first non-empty line; ``language`` defaults to a trailing
    ``_xx`` filename token. Remaining ``Document`` fields are optional metadata
    and pass straight through.
    """
    path = Path(path)
    lines = _normalize(path.read_text(encoding="utf-8"))

    document = Document(
        id=path.stem,
        source_company=source_company,
        title=title if title is not None else _derive_title(lines),
        doc_type=doc_type,
        publication_date=publication_date,
        period_covered=period_covered,
        url=url,
        language=language if language is not None else _infer_language(path.stem),
    )
    return LoadedReport(document=document, text="\n".join(lines), lines=lines)
