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

- Golden labels are hand-made from the Novartis / GSK / Takeda reports; treat
  `evals/golden/` as ground truth — change it deliberately, never to chase a
  score.
- Make scores reproducible and diffable across runs (pin inputs, record model +
  prompt version).
- LLM-as-judge prompts are versioned artifacts; changing them is a scored event.

## Gotchas

_None yet._
