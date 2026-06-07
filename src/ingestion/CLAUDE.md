# CLAUDE.md — `src/ingestion`

## Purpose

Load markdown reports from `data/reports/`, apply light normalization, and
**section-aware chunk** them. v1 is **markdown-only** — PDF download /
`pdfplumber` / PDF→markdown are deferred (see `docs/ARCHITECTURE.md`).

- `loader.py` — `load_report(path, *, source_company, doc_type, ...) -> LoadedReport`
  (`Document` metadata + cleaned text/lines; the `Document` schema has no content
  field, so the text travels alongside it).
- `chunker.py` — `chunk_document(loaded, ChunkConfig) -> list[Chunk]`.

Downstream contract: each `Chunk` carries provenance sufficient to build
`schema.SourceRef` — `document_id`, section/header path, 1-based inclusive
`line_range`, and the verbatim snippet. Extraction (next step) consumes chunks;
this module does **not** call any LLM.

## Run & test

```bash
pytest tests/ingestion -q
```

## Conventions

- **Character-based** chunking with overlap (no tokenizer dependency — see
  `docs/LEARNINGS.md` 2026-06-07). Keep `chunk_size` + `overlap` configurable via
  `ChunkConfig`.
- Chunk on markdown structure (headers) first; **pack** small consecutive
  sections up to the size budget; char-window + overlap only **within** an
  oversized section.
- Cleaning is line-stable: provenance line numbers index `LoadedReport.lines`, so
  keep `snippet` and `line_range` consistent with those canonical lines.

## Gotchas

- Table-derived markdown (e.g. the Takeda pipeline) emits many noise `##`
  "headers" (single cells like `## ★`). Section **packing** is what stops that
  from exploding into hundreds of one-line chunks; the header breadcrumb is only
  as meaningful as the source's actual structure.
