# CLAUDE.md — `src/agent`

## Purpose

A **single research agent**: a planning loop, tool definitions, and synthesis
that **cites sources**. Tools:

- `corpus_retrieve` — hybrid retrieval over the indexed corpus (`src/rag`).
- `clinicaltrials_lookup` — live ClinicalTrials.gov (`src/tools`).
- `fda_lookup` — live FDA/EMA (`src/tools`).

Out of scope for now: multi-agent orchestration (deferred).

## Run & test

```bash
pytest tests/agent -q              # planning/synthesis tests (added in Phase 4)
# Agent CLI entry point TBD (Phase 4)
```

## Conventions

- Every claim in a synthesized answer must carry a citation traceable to a
  `schema.SourceRef` or a live-tool result — the groundedness eval enforces this.
- Keep the planning loop bounded (max steps) and tool calls typed.
- Tool I/O uses Pydantic models; no freeform prose contracts between steps.

## Gotchas

_None yet._
