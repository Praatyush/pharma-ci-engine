# CLAUDE.md — `src/rag`

## Purpose

Embeddings, FAISS index **build / persist / load**, the `id -> chunk / record`
mapping (FAISS stores vectors only, so this mapping is our responsibility), and
**hybrid retrieval** (semantic + keyword/BM25 via `rank-bm25`).

Hybrid is essential here: **BM25** earns its place because **drug codes + endpoint
acronyms are exact tokens dense retrieval blurs** — e.g. `VAYHIA`, `TAK-861`,
`Lp(a)` (NOT NCT IDs: this corpus has **zero**). **Dense** adds semantic
disambiguation — Q5's iptacopan-against-the-wrong-indication trap (iptacopan for
myasthenia gravis vs IgA nephropathy) is the live example that sparse-alone is
insufficient.

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
- **Retrieval legs + scorer are BUILT and merged** (Phase 3 complete): chunk leg
  (`src/rag/chunk_leg.py` + `units`/`embeddings`/`dense`/`sparse`), entity leg
  (`src/rag/entity_leg.py`), span-keyed fusion (`src/rag/fusion.py`), and the shared scorer
  (`src/evals/retrieval_scorer.py`). The golden JSON is the eval contract; the design is locked in
  `docs/RETRIEVAL_PLAN.md` (see next section) — build against it, do not redesign here.

## Retrieval design (Phase 3 — LOCKED; build reference: `docs/RETRIEVAL_PLAN.md`)

Operating locks for this module (full plan + gate artifacts in `docs/RETRIEVAL_PLAN.md`):

- **Staged + gated:** Stage A (chunk leg = baseline + reachability backbone) → Gate A → Stage B
  (entity leg — lean, layered, **null contribution acceptable**). The **shared scorer lives in
  `src/evals/`** (reuses `normalize` + `grounding` overlap helpers), built once and reused by both
  stages; **`src/rag/` holds the retriever only** (rag = retrieval, evals = scoring).
- **Retrieval units:** chunk units **reuse the ingestion chunker at 1500/200** (Stage A); entity
  units are serialized facts whose `line_range` is the **source chunk's** range (chunk-grained — no
  finer localization than the chunk leg). Every unit carries `(doc_id, line_range)` for the scorer
  to overlap-test against the golden.
- **Embeddings: `fastembed`** (local, reproducible, quota-free). `embeddings.py` is the **SOLE**
  importer (mirror `extraction/gemini_client.py` `_require_env`); `EMBED_MODEL` configurable; persist
  the FAISS index + `id→unit` map to gitignored `data/rag/`, recording embedding model + version
  (re-embed on change).
- **Fusion: RRF, `k_rrf=60`**, no score normalization, no tunable weight.
- **Metrics:** recall@k over k ∈ {1, 3, 5, 10}, **sliced by query type + extracted/un-extracted**;
  operating-k deferred to Phase 4.
- **T (containment threshold) is decided at Gate A**, not now — may prove structurally inert at
  chunk grain, in which case that is **reported as a finding** (see `docs/LEARNINGS.md` 2026-06-11).
- Deps (`faiss-cpu`, `rank-bm25`, `fastembed`) are added at **Stage-A start, with approval** — not yet.

## Run & test

```bash
pytest tests/rag -q                       # module tests
python -m src.evals.retrieval_run         # Gate A — chunk-leg recall@k eval (builds/loads data/rag/)
python -m src.evals.retrieval_gate_b      # Gate B — chunk/entity/fused three-way decomposition
# The two eval commands require the gitignored corpus (data/reports/) + extraction artifacts
# (data/eval/extractions/) to be present; how to obtain the corpus is deferred to the README.
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
