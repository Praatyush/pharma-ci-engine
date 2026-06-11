# pharma-ci-engine

A **multi-therapeutic-area pharma competitive-intelligence engine**. It ingests
dense pharma documents and live clinical/regulatory data, extracts them into a structured
domain model, retrieves over that corpus, and answers competitive-intelligence
questions with **grounded, cited** output — all measured by an offline eval
harness.

The focus is **product-level clinical-lifecycle intelligence**: pipeline phase,
clinical endpoints, trial status, regulatory timelines, and competitive
benchmarking — not generic financial summary.

## Pipeline

```
markdown ─▶ ingestion ─▶ extraction ─▶ ┌─ rag   (FAISS + hybrid retrieval)
            (load,        (LLM →         └─ evals (offline scoring)
             char-chunk)   schema)            │
                                              ▼
                                       agent (plan · call tools · cite)
                                              ▼
                             grounded, cited CI answers
```

- **`src/ingestion/`** — load markdown from `data/reports/`, clean, section-aware
  **character-based** chunk with overlap.
- **`src/schema/`** — Pydantic v2 domain model (Document, SourceRef, Asset,
  Program, Trial, RegulatoryEvent, MarketMetric).
- **`src/extraction/`** — LLM structured-output extraction into the schema.
- **`src/rag/`** — embeddings, FAISS index, hybrid (semantic + BM25) retrieval.
- **`src/evals/`** — golden set + extraction-accuracy, groundedness, retrieval,
  and domain-relevance scoring.
- **`src/agent/`** — research agent: plan, call tools, synthesize with citations.
- **`src/tools/`** — live API clients (ClinicalTrials.gov, FDA/EMA).

## Tech stack

Python 3.11+ · Gemini SDK (LLM + embeddings) · FAISS · `rank-bm25` ·
Pydantic v2 · httpx · pytest. CLI / library-first — no GUI, no packaging.

## Quickstart

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # fill in real keys locally; never commit .env
set -a; source .env; set +a   # load .env into the shell (no python-dotenv)
pytest                        # run the test suite
```

## Documentation

- **`docs/ARCHITECTURE.md`** — target system design (source of truth).
- **`CLAUDE.md`** — operating rules, conventions, self-improvement protocol.
- **`docs/LEARNINGS.md`** — running log of bug fixes and gotchas.
- **`docs/V0_ARCHITECTURE.md`** — the deprecated v0 prototype (context only).

## Status

Phase 1 complete (schema → ingestion → extraction); on branch `phase-2-evals`.
Built in phases — see `ARCHITECTURE.md` → "Build order".
