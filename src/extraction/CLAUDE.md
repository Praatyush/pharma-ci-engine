# CLAUDE.md — `src/extraction`

## Purpose

Per-chunk Gemini extraction from ingestion `Chunk`s into `src/schema` fact
entities (`Asset`, `Program`, `Trial`, `RegulatoryEvent`, `MarketMetric`). This
module encodes the multi-TA pharma-CI domain.

- `gemini_client.py` — the **only** file importing `google.genai`. Key + model
  from env (`GEMINI_API_KEY`, `GEMINI_MODEL`); structured-output call wrapper;
  hand-rolled retry on 429 (long backoff) + 503 (short backoff), all else
  re-raised.
- `models.py` — extraction-view payload models (`response_schema` targets):
  schema fact entities **minus** `source_ref`/`id`, plus a per-item `evidence`
  quote. No `google.genai` import.
- `extractor.py` — the prompt, the per-chunk loop, and the payload→schema mapping
  (id assignment, asset linking by slug, `SourceRef` grounding). No `google.genai`
  import.

## Run & test

```bash
pytest tests/extraction -q     # unit tests — the SDK call is mocked (no key/network)
# Live run requires:  set -a; source .env; set +a
```

## Conventions

- **Structured output only** (`response_schema` bound to Pydantic), never
  free-text-then-parse-JSON. If Gemini's schema converter rejects the nested
  container, flatten the model shape — do not fall back to JSON parsing.
- `source_ref` and `id` are **code-assigned from the chunk**, never
  model-generated — that is what keeps grounding from being hallucinated.
- Grounding is `line_range` + `snippet` (the model's `evidence` quote is used only
  if it is a verbatim substring of the chunk; else the chunk text). `section_path`
  is decorative, not load-bearing (see `docs/LEARNINGS.md`).
- Open-vocab fields stay free-text in the prompt — suggest vocab, never coerce.
- `temperature=0` for deterministic extraction; keep the model name in env.

## Gotchas

- **Duplicate assets are expected, not a bug.** Per-chunk means an asset spanning
  N chunks is extracted N times; cross-chunk dedup / alias resolution is deferred
  to assembly (Phase 2+). See `docs/LEARNINGS.md`.
- `Program.as_of_date` is required by the schema but stated once per document
  (not per row), so the document snapshot date is **caller-supplied** in v1
  (`as_of_date=`); body-text auto-extraction is deferred.
