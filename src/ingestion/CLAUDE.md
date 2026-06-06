# CLAUDE.md — `src/ingestion`

## Purpose

Download PDFs, extract text with `pdfplumber` (upgrade table handling for
clinical/financial tables), clean, and **token-based chunk with overlap**.

Salvages v0's download helper (`requests`/`httpx` + UA header) and pdfplumber
extraction — but the chunker is **rewritten**: token-based with overlap, **not**
v0's ~2500-word splitter. No map-reduce, no whole-document summarization.

Downstream contract: emit clean chunks each carrying enough provenance
(`document_id`, `page`) to populate `schema.SourceRef` later.

## Run & test

```bash
pytest tests/ingestion -q          # module tests (added in Phase 1)
# CLI entry point TBD (Phase 1)
```

## Conventions

- Token-based chunking with overlap; keep chunk size + overlap configurable.
- Harden download error handling (timeouts, non-200, content-type).
- Preserve page numbers through extraction for citations.

## Gotchas

_None yet._
