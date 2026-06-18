# Architecture

This document describes how pharma-ci-engine is built: its data flow, its domain model, and the architecture of its retrieval, agent, and evaluation components. It is a technical reference for the completed system. For the project's motivation and headline results see the [README](../README.md); for the measurement narrative see the [evaluation case study](EVALUATION_CASE_STUDY.md); for the reasoning behind the major design choices see [engineering decisions](ENGINEERING_DECISIONS.md).

## 1. Overview

pharma-ci-engine is a pharmaceutical competitive-intelligence system that turns dense, unstructured company reports into grounded, cited answers. It combines structured extraction, hybrid retrieval, a research agent, live regulatory tools, and a deterministic evaluation framework.

It answers questions like what stage a drug is in, whether a trial met its endpoint, or when an approval was granted — from a corpus of industry documents, escalating to live regulatory sources when the corpus cannot support an answer, and citing every claim. A theme runs through the whole build and explains many of the choices below: the language model is given only the decisions that genuinely need judgment, and everything testable — control flow, scoring, citation resolution — is kept in code. The system is multi-therapeutic-area by design; breadth comes from the corpus, not from a larger schema.

## 2. End-to-end flow

```text
                  ┌─────────────┐
   markdown ─────▶│  ingestion  │  load · clean · character-chunk (size 1500 / overlap 200)
                  └──────┬──────┘
                         ▼
                  ┌─────────────┐
                  │ extraction  │  LLM structured outputs → typed domain model
                  └──────┬──────┘     (citations assigned by code, not the model)
                         ▼
              ┌──────────┴───────────┐
              ▼                      ▼
       ┌────────────┐         ┌────────────┐
       │  retrieval │         │   evals    │  deterministic scorer over
       │ chunk leg  │         │ (offline)  │  hand-authored golden sets
       │ + entity   │         └────────────┘
       │ leg, fused │
       └──────┬─────┘
              ▼
       ┌─────────────────────────────────────────────┐
       │                  agent                       │
       │  PLAN → [RETRIEVE → ASSESS]                   │
       │              │                               │
       │              ├─ sufficient → SYNTHESIZE      │
       │              ├─ gap → DISPATCH (live tool) ───┼──▶ loops back to RETRIEVE
       │              └─ exhausted → refuse            │
       └──────────────────────┬──────────────────────┘
                              ▼
                  grounded, cited competitive answers
```

Data moves through five stages, and the rest of this document drills into them in order.

**Ingestion** (`src/ingestion/`) loads markdown reports from `data/`, cleans them, and chunks them character-based with overlap. Markdown is the only ingested format; PDF ingestion is a deliberate deferral (§8).

**Extraction** (`src/extraction/`) runs structured-output LLM calls that map chunk text into the typed domain model (§3). The model proposes entities and field values; the citation linking each fact to its source span is assigned by code, never by the model.

**Retrieval** (`src/rag/`) indexes the corpus two ways — a chunk leg over raw passages and an entity leg over extracted facts — and fuses them (§4).

**The agent** (`src/agent/`) plans sub-queries, retrieves, assesses sufficiency, escalates to live tools on a genuine gap, and synthesizes a cited answer (§5).

**Evaluation** (`src/evals/`) is the offline harness that scores extraction, retrieval, and the agent against hand-authored golden datasets, deterministically (§6).

## 3. Domain schema

The schema is the contract the whole system is organized around: extraction populates it, retrieval indexes it, the evaluator scores against it, and the agent cites through it. It is optimized, in priority order, for extraction reliability, evaluation quality, and simplicity — over maximum coverage. It is implemented in Pydantic v2 (`src/schema/`), with unknown fields forbidden.

Seven entities: two provenance types, one noun, four dated fact entities.

**Provenance.** `Document` describes a source artifact (company, title, type, dates, URL). `SourceRef` pins a fact to a location — `document_id`, optional `page` / `section` / `line_range` (markdown and tables have no fixed pages, so a fact uses whichever applies), a `snippet`, and an `as_of_date`. Every fact entity carries a `SourceRef`; this is non-negotiable, because it is what makes both citation and the faithfulness evaluation possible.

**The noun.** `Asset` is a drug as a molecule: identifiers (generic name, development codes, brand names, aliases), owning and originating companies as plain strings, and molecular properties (target, mechanism, modality, route). A validator requires at least one identifier. Indication is deliberately *not* on `Asset` — one molecule is pursued across many indications, so indication lives on the development fact, not the noun.

**The fact entities**, each carrying a `source_ref`:

- `Program` — a dated development fact: one asset, in one indication and region, at one lifecycle stage, with therapeutic area, line of therapy, status, and formulation. This is the native shape of a pipeline-table row.
- `Trial` — a clinical trial: optional name and NCT id, the asset(s) studied, indication, phase, comparator, primary endpoint and whether it was met, significance, result, and readout date.
- `RegulatoryEvent` — a regulatory action: asset, agency, region, action, optional status, date, and indication.
- `MarketMetric` — a quantitative fact: a subject (an asset or a company), the metric, value, unit, optional currency and basis, period, and geography.

**Closed enums vs. open free-text** is the schema's central reliability lever. Fields with a genuinely closed, stable vocabulary are **closed enums**, scored by exact match: document type, region, program stage (`preclinical` through `P3`, plus `filed`/`approved`/`discontinued`), trial phase, regulatory agency and action, and market-metric type and basis. Fields with open-ended vocabulary stay **plain strings, never coerced to an enum**: `therapeutic_area`, `indication`, `target`, `modality`, `mechanism_of_action`, `primary_endpoint`. Each carries a *suggested* vocabulary in its description to steer extraction, but an out-of-vocabulary value passes through verbatim rather than being dropped or forced into a bucket. This is the deliberate mechanism for covering every therapeutic area without sacrificing per-field extraction reliability — breadth lives in the corpus and flows through these open fields, not in an ever-growing set of entity types. (Why these fields resist enumeration is in [engineering decisions](ENGINEERING_DECISIONS.md).)

A few modeling rules carry weight beyond the field lists:

- **Asset and Program are different things** — a noun (one molecule) versus a dated fact (one asset, one indication and region, one stage). One asset maps to many programs, mirroring how pipeline tables are shaped.
- **Stage and phase are different axes, not collapsed** — a program's `stage` is an asset's lifecycle in an indication and region; a trial's `phase` is a specific study's phase. An asset can be `filed` while a confirmatory phase-3 trial still runs.
- **Companies are plain strings, not an entity** — company-level views are derived by grouping on the company string; there is no competitor entity.
- **Document date and fact date are distinct** — `as_of_date` on `SourceRef` is the document's snapshot date; on `Program` it is the date that specific fact holds true. These usually coincide but can diverge, and collapsing them would lose that distinction.

## 4. Retrieval system

Retrieval is hybrid and two-legged, and the two-legged design is itself a result of evaluation. The baseline was strong on direct lookups but weak on questions that aggregate scattered facts across a document; the entity leg was introduced to target exactly that failure, because structured facts concentrate what long passages dilute (the diagnosis and its payoff are in the [case study](EVALUATION_CASE_STUDY.md)).

**The two legs** index the same corpus differently. The **chunk leg** (`src/rag/chunk_leg.py`) indexes raw passages built from the ingested markdown. The **entity leg** (`src/rag/entity_leg.py`) indexes the *extracted facts* from the schema — structured records rather than prose.

**Each leg is itself hybrid**, combining dense and sparse retrieval:
- **Dense** (`src/rag/dense.py`) is a FAISS flat inner-product index over L2-normalized vectors (cosine similarity), persisted alongside an id-to-unit map (FAISS stores vectors only, so the mapping back to source text is maintained separately). Embeddings (`src/rag/embeddings.py`) use a pinned local model (`BAAI/bge-small-en-v1.5`) — local and quota-independent, which keeps retrieval reproducible and free of API dependence.
- **Sparse** (`src/rag/sparse.py`) is BM25, which keeps exact tokens whole. This matters in pharma: drug development codes and endpoint acronyms are exact tokens that pure vector search blurs.

**Fusion** (`src/rag/fusion.py`) combines the legs with reciprocal-rank fusion keyed on the source span (document id plus line range), at a fixed `k_rrf = 60`. RRF is deliberately parameter-free in the way that matters: there is no tunable weight balancing dense against sparse. With a small evaluation set, a tuned weight could not be set honestly, so the system uses a method that needs none (the reasoning is in [engineering decisions](ENGINEERING_DECISIONS.md)).

The agent reaches retrieval through a single corpus tool (`src/agent/retrieval.py`) that unions the chunk leg and the fused result, deduplicates by span, and caps the returned evidence — a fixed retrieval depth the model does not control.

## 5. Research agent

The agent is the system's endpoint and its most distinctive component. It answers a question by running a code-owned loop while delegating three narrow judgments to the model.

### The loop

```text
PLAN  ──▶  RETRIEVE  ──▶  ASSESS  ──┬─ sufficient ──▶  SYNTHESIZE
            ▲                       │
            │                       ├─ gap ──▶  DISPATCH (live tool)  ──┐
            └───────────────────────┼──────────────────────────────────┘
                                    └─ exhausted / budget hit ──▶  refuse
```

### What the model decides, and what the code decides

```text
Model-owned (judgment)             Code-owned (deterministic)
────────────────────────           ──────────────────────────
PLAN       question → sub-queries   loop control + iteration budget (3)
ASSESS     evidence → verdict       stopping rule + terminal-state assignment
SYNTHESIZE evidence → claims        gap → tool dispatch (routing)
                                    citation resolution
                                    evaluation
```

This boundary is the point. A control flow written in code can be run, measured, and trusted to behave the same way twice; a model improvising its own control flow can only be hoped about. The model never sees a document's identity and never declares the run finished. Drawing the line here also makes failures legible — when the agent gets something wrong, it can be localized to either the model's judgment or the code around it, and those are different bugs (the reasoning is in [engineering decisions](ENGINEERING_DECISIONS.md)).

### Corpus-first, then escalate

The agent answers from the corpus when the corpus can support an answer, and escalates only on a genuine gap. The assess step returns a verdict — `sufficient`, `gap`, or `exhausted` — and, on a gap, a `gap_kind` that classifies what is missing. Code maps that classification to an action: a corpus gap re-queries the corpus, a trial-status gap dispatches the ClinicalTrials.gov client, and a regulatory-status gap dispatches the openFDA client. After a dispatch, the new evidence loops back through retrieve and assess. The escalation is a code-owned routing decision driven by the model's classification, not a tool call the model makes directly.

### Terminal states

The terminal state is assigned by code, never emitted by the model, and is one of three: `answered`, `partially_answered`, or `insufficient_evidence`. It is computed from whether the iteration budget was hit, whether any evidence was gathered, how many synthesized claims survived citation resolution, and the final assess verdict. When the corpus is silent and no tool can fill the gap, the agent refuses rather than fabricating — and because that decision lives in code rather than model discretion, it is measurable.

### Evidence and citations

Retrieved evidence is accumulated into a span-deduplicated, numbered list. The model cites by integer index into that list and nothing more — it never handles document ids or line ranges. After the run, a code-side step (`src/agent/resolve.py`) resolves each index back to its concrete source: a `(document, line_range)` span for a corpus claim. This separation is what lets the system check, deterministically, that every cited claim actually traces to the evidence the model was given.

### Running the agent

The agent is exposed as a CLI: `python -m src.agent.run "<question>"` builds the retriever and the live-tool stack, runs a single research query, and prints the terminal state and each claim with its citations resolved to a source span (or, for a tool-sourced claim, the external record's identity).

### 5.1 Live tools

The live tools exist because the agent can reach a real gap the corpus cannot fill; they are not an independent subsystem. There are two clients (`src/tools/`): a **ClinicalTrials.gov** client and an **openFDA Drugs@FDA** client. (EMA is not integrated.)

Two architectural details matter:

- **Injected transport.** Each client accepts an optional HTTP transport, defaulting to a real network transport. This seam is what makes the live behavior testable: the evaluation harness injects a mock transport that replays recorded responses, so a test exercises the exact client code path with no network and no API key (§6).
- **Record-identity citations.** An external API record is not a span of text, so a tool-sourced claim cannot cite a line range. Instead it cites the record's identity — a ClinicalTrials.gov registry id or an openFDA application number — with no line range. The citation-faithfulness check handles both modes: span containment for corpus claims, record-identity equality for tool claims.

## 6. Evaluation framework

The evaluation harness is the deliberate differentiator of the project, and its defining property is that it is **deterministic**: there is no LLM grading the system's output and no tunable threshold. Every number is produced by code a reader can inspect. This section describes how the harness is built; for what it found and the reasoning behind its design, see the [case study](EVALUATION_CASE_STUDY.md) and [engineering decisions](ENGINEERING_DECISIONS.md).

The harness scores against **hand-authored golden datasets** (`src/evals/golden/`) across the system's layers:

- **Extraction accuracy** (`src/evals/metrics.py`, with `matching.py`, `normalize.py`, `labels.py`) — per-entity-type precision, recall, and F1 against the golden facts. Closed-enum and identifier fields are scored by exact match; open free-text fields by a normalized match, since there is no taxonomy to grade them against exactly.
- **Extraction groundedness** (`src/evals/grounding.py`) — a deterministic check that a fact's salient tokens are actually present within its cited source span. This is token presence, not an LLM judgment.
- **Retrieval quality** (`src/evals/retrieval_scorer.py`, with `retrieval_run.py`) — span-containment and recall-at-k against a query-based golden governed by a locked relevance policy.
- **Agent metrics** (`src/evals/agent_metrics.py`) — terminal-state correctness, claim recall, claim precision, and citation faithfulness, plus a check that the agent refuses when it should. Citation faithfulness is deterministic: span containment for corpus claims and record-identity equality for tool claims, with no model in the loop.
- **The value layer** (`src/evals/agent_value_match.py`) — a deterministic canonicalizer and numeric comparator that decides when two field values match, so scoring does not depend on surface string identity.

**Fixture-backed live evaluation.** The agent's live-tool behavior is measured without network access or API keys. Each tool client exposes the injected-transport seam (§5.1); the harness injects an HTTP mock transport that replays recorded API responses (committed under `src/evals/fixtures/`), exercising the real client code over deterministic inputs. The agent golden sets include both a corpus-only set and a small live set whose entries encode the intended escalation behavior. A measurement that cannot be reproduced is not evidence, so the live evaluation is built to run identically every time.

## 7. Repository map

```text
pharma-ci-engine/
├── README.md                 # project front door
├── pyproject.toml            # dependencies + build + pytest config (single source; no requirements.txt)
├── .env.example              # template only — never commit a real .env
├── docs/
│   ├── ARCHITECTURE.md            # this document
│   ├── EVALUATION_CASE_STUDY.md   # the measurement narrative
│   ├── ENGINEERING_DECISIONS.md   # the reasoning behind the major choices
│   └── ...                        # internal design and working records
├── src/
│   ├── ingestion/    # load + clean + chunk markdown
│   ├── schema/       # the Pydantic v2 domain model
│   ├── extraction/   # structured-output LLM extraction into the schema
│   ├── rag/          # chunk leg + entity leg, dense (FAISS) + sparse (BM25), RRF fusion
│   ├── agent/        # the research-agent loop, seams, citation resolution
│   ├── tools/        # ClinicalTrials.gov + openFDA clients
│   └── evals/        # deterministic scorer, golden datasets, fixtures
│       ├── golden/
│       └── fixtures/
├── data/             # GITIGNORED: corpus markdown, extraction artifacts, FAISS index
└── tests/            # 144 tests across all components
```

Per-directory operating notes for the development tooling live in `CLAUDE.md` files at the root and in each `src/` module; they govern how the code agent runs and are intentionally separate from this design reference.

**Tech stack:** Python 3.11+, Gemini (LLM and structured extraction), FAISS, `rank-bm25`, a pinned `fastembed` model for embeddings, Pydantic v2, `httpx`, and `pytest`. Library- and CLI-first; no GUI, no packaging beyond `pyproject.toml`.

## 8. Deliberate deferrals and non-goals

Each of these is a scope choice made to protect extraction reliability, evaluation quality, and simplicity. They are documented as deliberate, and most are additive later without reshaping the core.

- **PDF ingestion** — markdown is the only ingested format; PDF download and PDF-to-markdown conversion are deferred.
- **A typed tool-failure layer** — tool clients raise and propagate on failure by design; a structured failure-result wrapper and the graceful routing around it are deferred rather than built without evidence they are needed (the reasoning is in [engineering decisions](ENGINEERING_DECISIONS.md)).
- **Cross-document entity resolution** — asset and company aliases are stored as observed, not merged across documents.
- **Multi-provider model abstraction** — the system runs on a single configured model provider; a provider-abstraction layer was deliberately not built.
- **Report mode and multi-agent orchestration** — the agent answers questions; longer-form report generation and multi-agent decomposition are deferred.
- **A richer entity set** — deal/M&A entities, a full company entity, biomarker and population fields, combination-regimen semantics, and loss-of-exclusivity tracking are all out of scope for now, and each can be added without reshaping the existing model.

This is a deliberately bounded system: it does the core competitive-intelligence task — grounded, cited answers from a corpus, augmented with live regulatory data, measured rigorously — and stops there on purpose.
