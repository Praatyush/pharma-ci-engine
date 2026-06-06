# ARCHITECTURE.md — Target System Design

> **Source of truth for system design.** Describes *what* the system is — its
> modules, data flow, schema, and build order.
> **Operating rules** (how to run/debug/deploy + the self-improvement protocol)
> live in `CLAUDE.md` (root) and the nested `CLAUDE.md` in each `src/` module,
> **not** here. See "Repository structure" below.
> Legacy context: `docs/V0_ARCHITECTURE.md`.

## Project

**`pharma-ci-engine`** (rename freely) — an **oncology competitive-intelligence
engine**. It ingests dense pharma documents and live clinical/regulatory data,
extracts them into a structured domain model, retrieves over that corpus, and
answers competitive-intelligence questions with **grounded, cited** output —
all measured by an offline eval harness.

This replaces v0's generic financial summarizer. The pivot — from financial
summary to **product-level clinical lifecycle intelligence** (pipeline phase,
clinical endpoints, trial status, regulatory timelines, competitive
benchmarking) — is the entire point of the rebuild and is encoded in the
domain schema below.

## System overview

```
                ┌─────────────┐
  PDFs ───────▶ │  ingestion  │  download · extract · clean · token-chunk
                └──────┬──────┘
                       ▼
                ┌─────────────┐
                │ extraction  │  LLM structured outputs → domain schema
                └──────┬──────┘
                       ▼
        ┌──────────────┴───────────────┐
        ▼                               ▼
 ┌─────────────┐                ┌──────────────┐
 │     rag     │  FAISS index   │    evals     │  golden set · accuracy ·
 │ (retrieval) │  + hybrid      │  (offline)   │  groundedness · retrieval ·
 └──────┬──────┘  search        └──────────────┘  domain-relevance
        ▼
 ┌─────────────┐
 │    agent    │  plan · call tools (corpus + live APIs) · synthesize w/ citations
 └──────┬──────┘
        ▼
   grounded, cited competitive-intelligence answers
```

## Modules (`src/`)

- **`ingestion/`** — download PDFs, extract text (pdfplumber; upgrade table
  handling), clean, and **token-based** chunk with overlap. Salvages v0's
  download + extraction; rewrites the chunker.
- **`schema/`** — the domain model (below). Pydantic models used for both
  structured-output extraction and typed storage.
- **`extraction/`** — LLM extraction from chunks into `schema` objects via
  structured outputs / function calling. This is what encodes the domain.
- **`rag/`** — embeddings, FAISS index build/persist/load, the `id -> chunk /
  record` mapping (FAISS stores vectors only, so this mapping is on us), and
  **hybrid retrieval** (semantic + keyword/BM25). Hybrid matters here: drug
  names, NCT IDs, and endpoint acronyms are exact tokens that pure vector
  search misses.
- **`evals/`** — the centerpiece. Golden dataset (`evals/golden/`), plus four
  layers: extraction accuracy (precision/recall vs. golden), groundedness /
  faithfulness (LLM-as-judge — every claim must trace to a source passage),
  retrieval quality (precision@k / recall@k), and a domain-relevance rubric
  (clinical signal vs. generic-financial noise). A regression runner scores
  every prompt/model change.
- **`agent/`** — single research agent: a planning loop, tool definitions, and
  synthesis that **cites sources**. Tools: `corpus_retrieve` (rag),
  `clinicaltrials_lookup`, `fda_lookup`.
- **`tools/`** — external API clients: ClinicalTrials.gov, FDA/EMA. Keeps the
  system current instead of limited to static PDFs.

## Domain schema (`src/schema/`)

The structured model that encodes the oncology-CI pivot. Pydantic v2 models:

- **`Drug`** — `name`, `generic_name`, `mechanism_of_action`,
  `target_indication`, `modality`, `company`.
- **`Trial`** — `nct_id`, `drug`, `phase` (1|2|3|4), `status`
  (recruiting|active|completed|terminated|...), `primary_endpoint_type`
  (PFS|OS|ORR|DFS|...), `endpoint_result`, `readout_date`, `indication`.
- **`RegulatoryEvent`** — `drug`, `agency` (FDA|EMA|...), `action`
  (approval|CRL|fast_track|breakthrough|withdrawal|...), `date`, `indication`.
- **`MarketMetric`** — `drug` | `company`, `metric`
  (revenue|market_share|growth_rate), `value`, `period`, `geography`.
- **`Competitor`** — `company`, `drugs: list[Drug]`, `focus_areas`.
- **`SourceRef`** — every extracted fact carries `document_id`, `page`,
  `snippet`. **Non-negotiable** — this is what makes citation and the
  faithfulness eval possible.

> Treat this schema as the contract. Extraction populates it; RAG indexes it;
> evals score against it; the agent cites through `SourceRef`.

## Tech stack

- Python 3.11+
- OpenAI SDK — LLM + `text-embedding-3-*` (keep model names configurable)
- **FAISS** (vector store) · `rank-bm25` (keyword leg of hybrid retrieval)
- **Pydantic v2** (schema + structured outputs)
- `pdfplumber` (extraction) · `httpx` / `requests` (downloads + API tools)
- **pytest** (tests + eval harness)
- No GUI, no packaging — CLI / library-first

## Repository structure

```
pharma-ci-engine/
├── CLAUDE.md                 # ROOT: operating rules + self-improvement protocol
│                             #   (source of truth; Claude Code reads it automatically)
├── README.md
├── .gitignore
├── .env.example              # template only — NEVER commit a real .env
├── requirements.txt
├── docs/
│   ├── ARCHITECTURE.md        # this file
│   ├── V0_ARCHITECTURE.md     # legacy brief (context only)
│   └── LEARNINGS.md           # append-only; the agent logs findings + bug fixes here
├── src/
│   ├── ingestion/    + CLAUDE.md
│   ├── schema/
│   ├── extraction/   + CLAUDE.md
│   ├── rag/          + CLAUDE.md
│   ├── evals/
│   │   ├── golden/            # hand-labeled golden dataset
│   │   └── CLAUDE.md
│   ├── agent/        + CLAUDE.md
│   └── tools/        + CLAUDE.md
├── data/                     # GITIGNORED: sample PDFs, FAISS index, scratch
└── tests/
```

### Where the project setup lives (the "is setup part of this file?" answer)
- **This file** owns the *layout* above and the *what* of each module.
- **`CLAUDE.md`** (root + nested) owns the *how*: run/debug/deploy commands,
  conventions, and the self-improvement protocol. Claude Code automatically
  reads the root `CLAUDE.md` and the nearest nested `CLAUDE.md` as it works in
  a given directory — that is the per-module-context mechanism.
- Separated on purpose — different audience (the agent, every session) and
  different change cadence. Bloating one file with both is the failure mode
  that makes agents ignore instructions wholesale.
- Standardized on Claude Code, so there is no `AGENTS.md` or `.cursor/rules/`.
  If another agent tool is ever added, `ln -s CLAUDE.md AGENTS.md` at the root
  restores cross-tool portability cheaply.

## Build order

Build in phases; checkpoint after each one. (The master setup prompt enforces
this — the agent should stop for review between phases, not run end-to-end.)

- **Phase 0 — Scaffold.** Create the repo structure above: root `CLAUDE.md`
  (source of truth) + a nested `CLAUDE.md` in each `src/` module, plus
  `.gitignore`, `.env.example`, `docs/LEARNINGS.md`, `requirements.txt`,
  `README.md`. Initial commit.
- **Phase 1 — Ingestion + schema + extraction.** Token-chunking; Pydantic
  schema; structured-output extraction into it.
- **Phase 2 — Evals + golden set (baseline).** Hand-label facts from the
  Novartis / GSK / Takeda reports; extraction accuracy + a first regression
  run. **Establish the baseline before "improving" anything downstream.**
- **Phase 3 — FAISS RAG.** Embeddings, index persistence, hybrid retrieval,
  corpus Q&A with citations; add retrieval evals + groundedness.
- **Phase 4 — Research agent + live tools.** Planning loop; `corpus_retrieve`,
  `clinicaltrials_lookup`, `fda_lookup`; cited synthesis.

## Non-goals (out of scope for now)

- Multi-agent orchestration (deferred to a later phase).
- Production deployment, auth, multi-tenancy.
- Real client data — use public pharma reports + ClinicalTrials.gov / FDA.
