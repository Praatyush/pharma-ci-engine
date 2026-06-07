# ARCHITECTURE.md — Target System Design

> **Source of truth for system design.** Describes *what* the system is — its
> modules, data flow, schema, and build order.
> **Operating rules** (how to run/debug/deploy + the self-improvement protocol)
> live in `CLAUDE.md` (root) and the nested `CLAUDE.md` in each `src/` module,
> **not** here. See "Repository structure" below.
> Legacy context: `docs/V0_ARCHITECTURE.md`.

## Project

**`pharma-ci-engine`** (rename freely) — a **multi-therapeutic-area pharma
competitive-intelligence engine**. It ingests dense pharma documents and live
clinical/regulatory data, extracts them into a structured domain model,
retrieves over that corpus, and answers competitive-intelligence questions with
**grounded, cited** output — all measured by an offline eval harness.

This replaces v0's generic financial summarizer. The pivot — from financial
summary to **product-level clinical lifecycle intelligence** (pipeline stage,
clinical endpoints, trial status, regulatory timelines, competitive
benchmarking) — is the entire point of the rebuild and is encoded in the
domain schema below.

### Therapeutic-area scope

**Multi-TA by design — not oncology-only.** The corpus (e.g. the Takeda pipeline
table and the Novartis Q1-2026 report) spans oncology, immunology, neuroscience,
gastroenterology, rare disease, vaccines, cardiometabolic, and more — and
**breadth comes from the corpus, not from more entity types.** To capture every
TA while keeping per-field extraction reliable, the schema uses **open free-text**
for the fields whose vocabulary is genuinely open-ended (`therapeutic_area`,
`indication`, `target`, `modality`, endpoint) and retains **closed enums** only
where the vocabulary is genuinely closed and stable (trial `phase`, program
`stage`, regulatory `agency` and `action`, `region`). Oncology stays a useful
worked example (notably its rich endpoint vocabulary) — now one area among many.

## System overview

```
                ┌─────────────┐
  markdown ───▶ │  ingestion  │  load · clean · token-chunk
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

- **`ingestion/`** — load markdown reports from `data/reports/`, clean, and
  **token-based** chunk with overlap. v1's canonical (and only) document format
  is markdown; PDF ingestion is deferred (see note below).
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
  (clinical signal vs. generic-financial noise). Extraction accuracy scores
  closed-enum and ID fields by **exact match** and the open free-text fields
  (`therapeutic_area`, `indication`, `target`, `modality`, endpoint) by
  **normalized/fuzzy match**. A regression runner scores every prompt/model
  change.
- **`agent/`** — single research agent: a planning loop, tool definitions, and
  synthesis that **cites sources**. Tools: `corpus_retrieve` (rag),
  `clinicaltrials_lookup`, `fda_lookup`.
- **`tools/`** — external API clients: ClinicalTrials.gov, FDA/EMA. Keeps the
  system current instead of limited to static reports.

> **Deferred to a later iteration (deliberate scope cut, not an oversight):**
> PDF URL ingestion, PDF download, and PDF→markdown conversion. v1's canonical
> and only document format is markdown — ingestion reads the markdown reports
> already in `data/reports/`. `pdfplumber` returns to the tech stack when PDF
> ingestion does.

## Domain schema (`src/schema/`)

The structured model that encodes the multi-TA pharma-CI pivot — **7 entities**,
described here as field lists (the Pydantic v2 implementation is Phase 1, per the
build order). The model is optimized, in order, for **(1) extraction reliability,
(2) evaluation quality, (3) simplicity** — explicitly over maximum coverage.
Breadth comes from the corpus (many TAs), not from more entity types.

Two are provenance types (`Document`, `SourceRef`); one is a noun (`Asset`); four
are dated fact entities (`Program`, `Trial`, `RegulatoryEvent`, `MarketMetric`).
**Every fact entity carries a `SourceRef`** — non-negotiable; it is what makes
citation and the faithfulness eval possible.

### Provenance

- **`Document`** — `id`, `source_company`, `title`, `doc_type`,
  `publication_date`, `period_covered`, `url`, `language`. The source artifact a
  fact was extracted from.
- **`SourceRef`** — `document_id`, `locator` (flexible: `page?` | `section?` |
  `line_range?` — markdown and tables have no fixed pages), `snippet`,
  `as_of_date` (the snapshot date the source states, e.g. "as of May 13, 2026").
  Attached to **every** fact below.

### Noun

- **`Asset`** (a drug as a noun — one molecule) — `id`, `generic_name`,
  `development_codes[]`, `brand_names[]`, `aliases[]`, `company` (string owner),
  `originator_company` (string, optional), `target`, `mechanism_of_action`,
  `modality`, `route` (optional). **`indication` is NOT on `Asset`** — one asset
  is pursued across many indications; that lives on `Program`.

### Fact entities (each carries `source_ref`)

- **`Program`** (a dated development fact: asset × indication × region × stage) —
  `id`, `asset_id`, `therapeutic_area`, `indication`, `line_of_therapy`
  (optional), `region`, `stage`, `status_reason` (optional), `formulation`
  (optional), `as_of_date`, `source_ref`. This is the native shape of a pipeline
  table row.
- **`Trial`** — `id`, `trial_name` (optional), `nct_id` (**optional**),
  `asset_ids[]`, `indication`, `phase`, `comparator` (optional),
  `primary_endpoint`, `met_primary_endpoint` (optional bool),
  `statistical_significance` (optional), `endpoint_result`, `readout_date`
  (optional), `region` (optional), `source_ref`.
- **`RegulatoryEvent`** — `asset_id`, `agency`, `region`, `action`, `status`
  (optional: `granted` | `pending` | `denied`), `date`, `indication`,
  `source_ref`.
- **`MarketMetric`** — `subject` (`asset_id` | `company` string), `metric`,
  `value`, `unit`, `currency` (optional), `basis` (optional), `period`,
  `geography`, `source_ref`.

### Closed enums (small, stable — kept strict; exact-match in evals)

- **`Document.doc_type`** — `pipeline_table` | `financial_report` |
  `press_release` | `other`
- **`region`** (Program · Trial · RegulatoryEvent) — `US` | `EU` | `JP` | `CN` |
  `Global` | `other`
- **`Program.stage`** — `preclinical` | `P1` | `P1/2` | `P2` | `P2a` | `P2b` |
  `P3` | `filed` | `approved` | `discontinued`
- **`Trial.phase`** — `1` | `1/2` | `2` | `2a` | `2b` | `3` | `4`
- **`RegulatoryEvent.agency`** — `FDA` | `EMA` | `PMDA` | `NMPA` | `MHLW` |
  `other`
- **`RegulatoryEvent.action`** — `filed` | `approval` | `CRL` |
  `priority_review` | `breakthrough` | `fast_track` | `orphan` | `PRIME` |
  `CHMP_opinion` | `application_withdrawal` | `product_withdrawal` | `other`
- **`MarketMetric.metric`** — `revenue` | `growth_rate` | `market_share` |
  `patient_count` | `country_count`
- **`MarketMetric.basis`** — `reported` | `constant_currency`

### Open free-text (multi-TA breadth lives here)

Each carries a **suggested** vocabulary in its field description to steer
extraction, but values are **never coerced to an enum** — out-of-vocab values
pass through **verbatim**. This is the deliberate mechanism for covering every TA
without sacrificing per-field reliability.

- **`therapeutic_area`** — suggested: oncology, immunology, neuroscience,
  gastroenterology, rare_disease, vaccines, cardiometabolic, …
- **`indication`** — free text.
- **`target`** — e.g. Claudin 18.2, TYK2, BCR-ABL, FRα, …
- **`modality`** — suggested: small_molecule, mAb, ADC, bispecific, radioligand,
  gene_therapy, cell_therapy, siRNA/RNAi, peptide, plasma_derived, vaccine, …
- **`primary_endpoint`** — suggested: PFS, OS, ORR, DFS, DOR, EFS, pCR, PASI,
  DLQI, HbA1c, EDSS, immunogenicity, … (oncology's rich endpoint set is the
  worked example here).

### Design rules

- **Asset vs Program.** An `Asset` is a noun (one molecule); a `Program` is a
  dated fact (one asset, one indication/region, one stage). One asset → many
  programs. This matches the native shape of pipeline tables.
- **`Program.stage` and `Trial.phase` are different axes — do not collapse
  them.** `stage` is the asset's lifecycle in an indication/region (including
  `filed`, `approved`, `discontinued`); `phase` is a specific trial's phase. An
  asset can be `filed` (stage) while a confirmatory phase-`3` trial still runs.
- **Companies are plain strings, not an entity.** There is no `Competitor`
  entity; company-level views (a competitor's portfolio, focus areas) are
  *derived* by grouping assets/metrics on their `company` string.
- **Aliases are stored as observed.** `Asset` and company aliases are recorded as
  they appear in each document; cross-document alias merging / entity resolution
  is **explicitly deferred** (not attempted in v1) — see below.
- **Temporal provenance: document-date vs fact-date.** `as_of_date` appears on
  both `SourceRef` and `Program` because they mean **different things**, not
  because one is a cached copy of the other. `SourceRef.as_of_date` is the source
  document's stated snapshot date (e.g. "as of May 13, 2026" on the Takeda table)
  — a property of the *document*. `Program.as_of_date` is the date that specific
  pipeline fact is true as of — a property of the *fact*. These usually coincide
  but can differ (a report published in April can restate a status current as of
  an earlier cutoff, or cite a readout from a specific prior date), so collapsing
  them would lose the ability to reason about a fact whose validity date differs
  from its document's date. Other facts carry their own event date —
  `RegulatoryEvent.date`, `Trial.readout_date`, `MarketMetric.period`.

> Treat this schema as the contract. Extraction populates it; RAG indexes it;
> evals score against it; the agent cites through `SourceRef`.

### Deferred / extension points (deliberate scope cuts, not oversights)

Each is cut to protect extraction reliability, eval quality, and simplicity, and
is additive later without reshaping the core:

- **Deal / M&A entity** — acquisitions, licensing, collaborations,
  rights/territory splits, deal financials (e.g. the Avidity acquisition and
  Takeda's partnership tables) are not modeled in v1.
- **Asset + company alias auto-resolution** — aliases are stored, not merged
  across documents.
- **Rich `Company` entity** — type / country / platforms; companies stay plain
  strings.
- **Biomarker / population fields** — e.g. "FRα-positive", pediatrics.
- **Combination / regimen modeling** — `Trial.asset_ids[]` can list the assets,
  but combination semantics (e.g. BrECADD) are not modeled.
- **Generic / biosimilar / loss-of-exclusivity tracking.**

## Tech stack

- Python 3.11+
- OpenAI SDK — LLM + `text-embedding-3-*` (keep model names configurable)
- **FAISS** (vector store) · `rank-bm25` (keyword leg of hybrid retrieval)
- **Pydantic v2** (schema + structured outputs)
- `httpx` / `requests` (live API tools) — `pdfplumber` (PDF extraction) returns
  when PDF ingestion does (deferred; see Modules → `ingestion/`)
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
  Novartis and Takeda reports; extraction accuracy + a first regression
  run. **Establish the baseline before "improving" anything downstream.**
- **Phase 3 — FAISS RAG.** Embeddings, index persistence, hybrid retrieval,
  corpus Q&A with citations; add retrieval evals + groundedness.
- **Phase 4 — Research agent + live tools.** Planning loop; `corpus_retrieve`,
  `clinicaltrials_lookup`, `fda_lookup`; cited synthesis.

## Non-goals (out of scope for now)

- Multi-agent orchestration (deferred to a later phase).
- Production deployment, auth, multi-tenancy.
- Real client data — use public pharma reports + ClinicalTrials.gov / FDA.
