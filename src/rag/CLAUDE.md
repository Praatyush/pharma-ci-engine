# CLAUDE.md — `src/rag`

## Purpose

Embeddings, FAISS index **build / persist / load**, the `id -> chunk / record`
mapping (FAISS stores vectors only, so this mapping is our responsibility), and
**hybrid retrieval** (semantic + keyword/BM25 via `rank-bm25`).

Hybrid is essential here: drug names, NCT IDs, and endpoint acronyms (PFS, OS,
ORR) are exact tokens that pure vector search misses.

## Retrieval golden + relevance policy (Phase 3 — LOCKED; eval contract, not a build)

- The retrieval eval scores against **`src/evals/golden/retrieval.golden.json`** (TRACKED;
  query-based + cross-document — distinct from the per-document extraction goldens). It is
  authored from the **source** reports, never from extraction output.
- **Relevance policy v2 is LOCKED**, embedded in that file (`policy_v2` + `validation_history`).
  Non-negotiables for any future scoring code: spans keyed **`(doc_id, line_range)`**; report
  **sliced** extracted vs un-extracted (never merge into one number); `resolution_limited` HITs go
  in a **separate slice** (never silently upgraded to clean); **§7** keeps unmodeled-entity
  (deal/M&A) content out of every recall denominator; the containment threshold **T is DEFERRED** —
  calibrate against the first real index, do **not** tune it from labels
  (see `docs/LEARNINGS.md` 2026-06-11).
- **No loader / eval code exists yet** (deliberate — built when the retriever does); the JSON is
  the contract. Retrieval **design** (retrieval units, embeddings, FAISS/BM25 + fusion) is the
  **next** conversation — do not add it here.

## Run & test

```bash
pytest tests/rag -q                # module tests (added in Phase 3)
# Index build + query CLI TBD (Phase 3)
```

## Conventions

- FAISS persists vectors only — always persist/load the id→record mapping
  alongside the index, and keep them in sync.
- Keep the embedding model name configurable; record which model built an index
  (re-embedding on model change is required).
- Hybrid scoring: combine semantic + BM25; keep the fusion method explicit and
  testable.

## Gotchas

_None yet._
