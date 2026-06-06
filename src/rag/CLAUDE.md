# CLAUDE.md — `src/rag`

## Purpose

Embeddings, FAISS index **build / persist / load**, the `id -> chunk / record`
mapping (FAISS stores vectors only, so this mapping is our responsibility), and
**hybrid retrieval** (semantic + keyword/BM25 via `rank-bm25`).

Hybrid is essential here: drug names, NCT IDs, and endpoint acronyms (PFS, OS,
ORR) are exact tokens that pure vector search misses.

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
