# RETRIEVAL_PLAN.md — Phase 3 retrieval, staged implementation plan (DESIGN-LOCKED)

> **Status (2026-06: superseded).** This was the design-time staged plan for Phase 3 retrieval, locked before implementation. Phase 3 is fully built and merged to main; this document is retained as a record of the plan as written, not as current status. For the system as actually built, see ARCHITECTURE.md and HANDOFF.md.
> This is the design-locked reference Stage A builds against. It owns the *retrieval* build plan;
> system design lives in `ARCHITECTURE.md`, run/debug rules in `CLAUDE.md` + `src/rag/CLAUDE.md`,
> the eval contract in `src/evals/golden/retrieval.golden.json` (relevance policy v2). No retrieval
> code, deps, or index exist yet — those are built per stage, gated.

## Locked decisions (Block 2 + the two Stage-A calls)

1. **Stage structure.** Chunk-leg **first** (Stage A = baseline + reachability backbone,
   independently shippable) → **Gate A** → entity leg (Stage B = lean, layered, measured by
   per-leg decomposition, **null contribution is acceptable**). The **shared scorer is built once**
   (in Stage A) and reused by both stages — this is what keeps the A-vs-B comparison
   apples-to-apples. Entity-only is disqualified as primary (two measured blindnesses: Vanrafia
   un-extraction, Q1 misclassification).
2. **Retrieval chunk granularity.** Stage A **reuses the existing 1500/200 ingestion chunk config**
   (`ingestion.chunker.ChunkConfig`, via `chunk_document`). Retrieval chunking is an *independent
   parameter* but is **NOT changed now**. Whether finer retrieval units are justified is a
   **Gate-A decision** made on the containment distribution + recall@k data. **T may prove
   structurally inert at chunk grain — if so, that is reported as a finding, not solved
   speculatively** (see §A.6).
3. **Embedding library:** **`fastembed`** (local, reproducible, quota-free, lightweight,
   interpretable — chosen for reproducibility/quota-independence/scale-calibration, **not** a
   quality claim). Isolated behind config (the `gemini_client.py` / `_require_env` pattern),
   `EMBED_MODEL` configurable; the persisted index **records embedding model + version**
   (re-embed on change).
4. **Score combination:** **RRF**, `k_rrf=60`, **no score normalization, no tunable weight**
   (weighted-fusion α is uncalibrable on this golden — the same reason T is deferred).
5. **Target-k:** **recall@k over k ∈ {1, 3, 5, 10}** as a curve, **sliced by query type** (and by
   extracted/un-extracted). Operating-k deferred to Phase 4.
6. **Module split:** retriever in **`src/rag/`**; shared scorer in **`src/evals/`** (matches the
   ARCHITECTURE rag=retrieval / evals=scoring boundary; the scorer reuses `normalize` +
   `grounding` overlap helpers).
7. **BM25 rationale (corrected):** BM25 earns its place because **drug codes + endpoint acronyms
   are exact tokens dense retrieval blurs** (`VAYHIA`, `TAK-861`, `Lp(a)`) — **NOT** NCT IDs (this
   corpus has zero). Dense adds **semantic disambiguation** (Q5's iptacopan-against-wrong-indication
   trap is the live example that sparse-alone is insufficient).

## Stage structure & gates

| | **Stage A — chunk leg** | **Gate A→B** | **Stage B — entity leg** |
|---|---|---|---|
| Builds | chunk units + dense + BM25 + RRF + **shared scorer** | — | entity units + dense + BM25 + RRF (same mechanism) + per-leg decomposition |
| Produces | sliced chunk-leg **recall@k curve + the T decision** | the Stage-A report | chunk-vs-entity-vs-fused decomposition + **entity Δrecall** |
| Why this order | locked baseline/backbone; complete & measurable alone | A's number must exist before B | B is defined *as a delta over A* |

Stage A is a complete Phase-3 result on its own. Stage B is meaningless without A's number to
measure against, so it is **gated behind A, not built beside it**.

## Shared scorer — `src/evals/retrieval_scorer.py` (built in Stage A, reused by Stage B)

The cross-cutting component and the place the build is most likely to go quietly wrong. Designed
**once**; both legs and both stages plug into it. Reimplementing overlap per leg would reintroduce
the exact confound the `(doc_id, line_range)` span-target exists to avoid.

- **Containment (§2):** `containment(span, unit) = |span_lines ∩ unit_lines| / |span_lines|`
  (answer-coverage direction, per lock). Pure line-range arithmetic over `(doc_id, line_range)`;
  `doc_id` must match (cross-doc keying). Reuses `grounding._cited_text` line logic — no second
  overlap implementation.
- **`span_hit(span, retrieved_units, T)`** → returns the hitting unit **plus the span's
  `resolution` tag**, so a hit via a `resolution_limited`-only span is flagged and reported in a
  separate slice, never silently upgraded to clean (§5).
- **§3 construct handlers**, dispatched on each query's `construct` field read from
  `retrieval.golden.json`: `single` (OR over a fact's span locations); `set-of-singles` (AND over
  facts, each OR over spans); `comparison` (**two scores** — presence = AND(entities)∘OR(assets)∘
  OR(locations); attribute = AND(assets)∘OR(locations); never collapsed); `aggregate`
  (recall-fraction = rows-hit / total-rows).
- **Slicing:** every number partitioned by `extracted | un-extracted` and by query `type`;
  `resolution_limited` hits separate. Never merged (§6).
- **Per-leg decomposition:** the scorer takes a *ranked unit list* and is agnostic to which leg
  produced it; run chunk-only / entity-only / fused → the deltas are the Stage-B finding.
- **Loads** `src/evals/golden/retrieval.golden.json`; treats Q2 as `scored:false` (§7 — never in a
  denominator).

## Stage A — chunk-leg retrieval

- **A.1 Chunk retrieval unit.** A `RetrievalUnit` wrapping an ingestion `Chunk`:
  `(doc_id, line_range, text)`. `line_range` comes free from `Chunk.line_range` (1-based inclusive)
  — the key the scorer overlap-tests against the golden.
- **A.2 Chunk index.** **Reuse `chunk_document()`** (don't write a second chunker) with the pinned
  **1500/200** config; retrieval `ChunkConfig` is conceptually an independent index parameter but
  is not changed now (lock 2). Buys determinism + tested code + `line_range`/`section_path` free.
- **A.3 Dense.** `src/rag/embeddings.py` is the **sole importer** of `fastembed`, reading
  `EMBED_MODEL` via `_require_env` (the `gemini_client.py` pattern). Local → no key, no quota,
  in-process query embedding. FAISS index = deterministic function of (chunk corpus, pinned
  `EMBED_MODEL`); **built once, persisted** to gitignored `data/rag/` with the `id→unit` map beside
  it (FAISS stores vectors only); metadata records model + version. Loaded per run, never
  re-embedded to iterate on scoring.
- **A.4 BM25.** `rank-bm25` over chunk text; tokenization **preserves exact tokens** (`TAK-861`,
  `VAYHIA`, `Lp(a)`) — lowercase but do not strip the alphanumerics that carry the drug-code /
  acronym signal. Cheap to rebuild in-memory at load (~134 chunks); persistence optional.
- **A.5 RRF.** `RRF(d) = Σ_legs 1/(k_rrf + rank_leg(d))`, `k_rrf=60`. A unit in only one list
  contributes only that list's term (no penalty, no imputation). Within Stage A, RRF fuses the
  dense and BM25 chunk lists into one ranked chunk list.
- **A.6 T-calibration (the T-problem, third appearance).** The lock says Stage A pins T against
  data — mechanically that only works if **retrieval units are finer than golden spans**, and with
  coarse 1500/200 chunks they usually are not: most golden spans are short (1–14 lines) and sit
  *inside* one ~80-line chunk; a non-overlapping neighbor chunk overlaps such a span by **0 lines**,
  so containment stays **bimodal (1.0/0.0)** even with real ranked retrieval, and `recall@k` reduces
  to "is the containing chunk in top-k." **Coarse units reproduce the containment-bimodality
  regardless of any labeler choice** — see LEARNINGS 2026-06-11. **Plan:** make T-calibration an
  explicit Stage-A sub-task that emits the *distribution* of max-containment over retrieved top-k
  per (query, span). At **Gate A**, decide with data: (a) if a usable fractional distribution
  exists, pin T there (never tuned to maximize recall); (b) if degenerate-bimodal, the lever is a
  finer retrieval `ChunkConfig` (decided then, not now); (c) if T is structurally inert at chunk
  grain, **report that as the finding** and pin T only via the long-span / aggregate / comparison
  cases. The golden needs no re-labeling — its spans are already semantic/sub-chunk, independent of
  chunk boundaries; Stage A simply swaps real ranked units for the labeling stand-in.

### Gate A artifact (reviewable)
A pinned, sliced report to gitignored `data/eval/reports/` (the Phase-2 baseline-report pattern):
**recall@{1,3,5,10} curve, sliced by query type and extracted/un-extracted**, the
`resolution_limited` slice separated, per-construct scores (Q4 aggregate recall-fraction; Q5 two
scores), **plus the pinned T (or the documented inertness finding) and its calibration evidence**
(containment distribution + the fractional cases inspected against source). Reviewed before any
entity work.

## Stage B — entity-leg retrieval (begins only after Gate A)

- **B.1 Entity retrieval unit — chunk-grained (nuance to honor).** A `RetrievalUnit` over a
  persisted extraction fact: `line_range = fact.source_ref.line_range`. **That range is the fact's
  source *chunk* range** (extraction code-assigns the chunk's range), so **entity units are
  chunk-grained, not finer**. Consequence: the entity leg offers **no finer spatial localization**
  than the chunk leg; its only possible contribution is **ranking/recall** (surfacing a relevant
  region the chunk text ranked low, via structured serialization), measured purely in the
  **extracted slice**.
- **B.2 Entity index + serialization (lossy, measured — not assumed).** Serialize each fact to a
  short text line (e.g. `asset | indication | region | stage | action | value`) and index it with
  the **same dense+BM25+RRF mechanism as Stage A**. **Lean = minimal serialization + identical
  retrieval mechanism, NOT a weaker one** — structural parity is what makes a null result
  *trustworthy* ("entity-awareness doesn't help here," not "the leg was crippled"). Serialization is
  flagged in the report as a lossy variable.
- **B.3 Per-leg decomposition (the gate).** Run the shared scorer three ways — chunk-only
  (= Stage A), entity-only, fused (RRF over the two legs' ranked lists) — and report **entity
  Δrecall@k** in the extracted slice. **Δ≈0 is the locked-acceptable null** and a valid result. Two
  locked predictions it tests concretely: **Vanrafia** (un-extraction → not in the entity index →
  entity leg necessarily 0; chunk leg only); **Q1 plasma** (misclassification → the reg-events *are*
  indexed, but typed as Program `stage` not `RegulatoryEvent`; whether a reg-status query retrieves
  them is exactly the serialization question).

### Gate B artifact (reviewable)
The decomposition report: chunk-only vs entity-only vs fused recall@k (sliced), the explicit entity
Δ (including Δ≈0), and the entity leg's behavior on the two blindness cases. Entity leg is kept,
dropped, or reshaped on this number.

## Experiment sequence

```
Build shared scorer ──► STAGE A: chunk dense+BM25+RRF ──► score vs golden ──► T decision (§A.6)
                                                                                    │
                                       [GATE A: sliced chunk recall@k + T decision]  ◄── review
                                                                                    │
                         STAGE B: entity index (serialize) ──► decompose chunk/entity/fused
                                                                                    │
                                   [GATE B: entity Δrecall, incl. acceptable ≈0]  ◄── review
```
T-calibration falls in **Stage A** (first real chunks). The entity-null-check falls in **Stage B**
(the decomposition *is* the null check). The scorer spans both but is built once, in A.

## The line_range bridge (most-likely-to-go-wrong — emphasized)

The golden keys spans by `(doc_id, line_range)`; both legs' units must carry a `line_range` the
**same** scorer overlap-tests. Chunk units → `Chunk.line_range`. Entity units →
`fact.source_ref.line_range` (chunk-grained — §B.1). The overlap logic lives in **one** function in
`retrieval_scorer.py`, used by both legs.

## Proposed module layout (responsibilities only — no code yet)

```
src/rag/
  units.py        # RetrievalUnit: (doc_id, line_range, text, kind, payload). Both legs emit this.
  embeddings.py   # SOLE importer of fastembed; EMBED_MODEL via _require_env (gemini_client.py pattern)
  dense.py        # FAISS build/persist/load + query; id->unit map persisted alongside
  sparse.py       # rank-bm25 over a unit corpus; exact-token-preserving tokenization
  fusion.py       # RRF (k_rrf=60); one-list-only handling
  chunk_leg.py    # Stage A: chunk units -> dense+BM25+RRF -> ranked chunk units
  entity_leg.py   # Stage B: serialized fact units -> dense+BM25+RRF -> ranked fact units
src/evals/
  retrieval_scorer.py   # SHARED: containment(§2/T) + §3 handlers + slicing + per-leg decomposition
  retrieval_run.py      # CLI: build/load index, run a leg (or fused), score, write sliced report
```

## Deps & docs identified (NOT actioned until Stage A, with approval)

- **Deps to add at Stage-A build start** (ask-before-adding rule): `faiss-cpu`, `rank-bm25`,
  `fastembed`. None added now.
- **Index persistence dir:** gitignored `data/rag/` (matches the `data/` discipline; never committed).
- **Doc note:** the stale `src/rag/CLAUDE.md` "NCT IDs" BM25 line is corrected as part of this
  persistence step (see lock 7).
