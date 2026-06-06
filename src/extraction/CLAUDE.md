# CLAUDE.md — `src/extraction`

## Purpose

LLM extraction from ingestion chunks into `src/schema` objects via **structured
outputs / function calling**. This module encodes the oncology-CI domain: it
populates `Drug`, `Trial`, `RegulatoryEvent`, `MarketMetric`, `Competitor`.

Every extracted fact must carry a `schema.SourceRef` (`document_id`, `page`,
`snippet`) — non-negotiable; it's what makes citation and the faithfulness eval
possible.

## Run & test

```bash
pytest tests/extraction -q         # module tests (added in Phase 1)
# Extraction CLI/entry point TBD (Phase 1)
```

## Conventions

- Use Pydantic v2 models as the structured-output schema; validate with
  `model_validate`.
- Keep the LLM model name configurable (env / config), never hardcoded.
- Prefer deterministic settings for extraction; make prompts versioned so the
  evals regression runner can attribute score changes.

## Gotchas

_None yet._
