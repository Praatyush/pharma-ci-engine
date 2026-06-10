# CLAUDE.md — `src/evals`

## Purpose

The centerpiece. A golden dataset (`evals/golden/`) plus four scoring layers:

1. **Extraction accuracy** — precision/recall vs. the golden labels.
2. **Groundedness / faithfulness** — LLM-as-judge; every claim must trace to a
   source passage.
3. **Retrieval quality** — precision@k / recall@k.
4. **Domain-relevance rubric** — clinical signal vs. generic-financial noise.

A **regression runner** scores every prompt/model change. Establish the baseline
(Phase 2) before "improving" anything downstream.

## Run & test

```bash
pytest tests/evals -q              # harness unit tests
# Regression runner CLI TBD (Phase 2)
```

## Conventions

- Golden labels are hand-made from the Novartis and Takeda reports; treat
  `evals/golden/` as ground truth — change it deliberately, never to chase a
  score.
- Make scores reproducible and diffable across runs (pin inputs, record model +
  prompt version).
- LLM-as-judge prompts are versioned artifacts; changing them is a scored event.

## Golden labeling policy (stated, not accidental)

These conventions make labeling reproducible across chunks. Record any per-chunk
deviation in that chunk's `note`.

- **(a) Dual-encode progress rows.** A pipeline progress-table row that states a
  regulatory action + date + region is labeled as BOTH a `Program` (the new stage)
  AND a `RegulatoryEvent` (the action). Every golden `RegulatoryEvent` sets
  **`from_progress_row`**: `true` for progress-row-derived, `false` for standalone
  prose. Reason: progress-row reg-events are co-located with a program and nearly
  free; counting them with standalone approvals/CRLs flatters aggregate reg-event
  recall (the headline metric). `metrics.py` reports standalone recall separately.
- **(b) Asset = any molecule named in the chunk.** Label every named molecule as an
  asset, including reference-only / footnote ones. No CI-relevance filter —
  reproducibility over judgment.
- **(c) No identifier, no label.** Section/target fragments with no in-chunk drug
  identifier (e.g. a bare `B7H3` target row) are NOT labeled; a prediction there is a
  legitimate false positive.
- **(d) Agency is a scored attribute, not a key.** It never blocks a match (demoted
  from the RegulatoryEvent key). For attribute scoring, **PMDA == MHLW** (same JP
  jurisdiction; review-vs-approve is bureaucratic) via
  `normalize.agency_attribute_matches`; all other agencies are distinct, so a
  declined/`other` agency scores as an attribute error.
- **(e) `indication` = DISEASE ONLY.** Population (pediatric), formulation (IV/SC/IT),
  dosing, and line-of-therapy are separate fields/attributes — **never** fold them into
  the indication string (it breaks the fuzzy key). E.g. "Pediatric Study (IT formulation
  for X)" → indication "X". (1L/2L may stay only where the source's indication cell
  literally includes it and it's the sole disambiguator.)
- **(f) Region-indeterminate.** A "-" (or blank) in a region column = the source states
  **no** region → label `region: null` (program kept, scored on asset+indication+stage;
  region dropped from the key). Do NOT manufacture `Global`/`other` — same discipline as
  the chunk-29 region-inferred exclusions; the predicted-side mirror is grounding's
  `inferred`. Only use an explicit region the source states (or spells out as "Global").

## Scoring rule (scope before collapse)

Scope **raw** predictions to the **union of labeled chunk indices**, collapse **once**
within that union, then match against the **union of golden labels**. Do not
collapse-then-scope, and do not sum per-chunk scores (a fact in two labeled chunks would
double-count). Asset precision/recall is **document-level** (assets carry no
`source_ref`). See `docs/LEARNINGS.md` 2026-06-10.

Before matching/collapsing `MarketMetric`s, fold company self-reference subjects to the
document's `source_company` via `normalize.fold_self_reference` (predicted AND golden) — the
company-level analog of `period -> reporting_period`. Standalone reg-event recall
(`from_progress_row=false`) is reported separately from progress-row reg-events.

## Gotchas

_None yet._
