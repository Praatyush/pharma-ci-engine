# HANDOFF.md

Running handoff log, updated at the end of every phase: work completed,
decisions, files changed, outstanding issues, and the recommended next step.

---

## Phase 2 (Stage 1) — Extraction persistence + Takeda baseline artifact (2026-06-09)

**Current authoritative state** (supersedes the Phase 1 entry below). Work continues on
branch **`phase-2-evals`**. Phase 2 is being built in two stages with a checkpoint
between; this is **Stage 1** — the scoreable extraction artifact — *before* the eval
harness itself.

### Work completed
- **Extraction persistence** — `src/extraction/persistence.py`: `save_extraction` /
  `load_extraction`, a versioned (`schema_version="1"`) self-describing JSON envelope
  (`meta` + `counts` + `result`) that round-trips an `ExtractionResult` losslessly.
- **Run CLI** — `src/extraction/run.py` (`python -m src.extraction.run --report takeda`):
  load → chunk → paced per-chunk extraction (4.5s) with progress logging → persist to
  `data/eval/extractions/` (gitignored via `data/`). Named presets for takeda/novartis;
  `--path/--company/...` overrides; `--limit` for a subset run.
- **`extract_document`** gained two backward-compatible kwargs: `delay_seconds=0.0`
  (proactive pacing, default off) and `on_chunk` (progress callback). Existing
  behavior/tests unchanged.
- Tests: **59 passing** (+4 persistence round-trip).

### Baseline artifact (the input Phase 2 scores against)
- `data/eval/extractions/qr2025_q4_Pipeline_table_en.extraction.json` — Takeda, full
  document, 34/34 chunks, zero failures. Model `gemini-3.1-flash-lite-preview`,
  git_sha `bace5ce`.
- Counts: **assets 150, programs 178, trials 5, regulatory_events 13, market_metrics 0**
  (assets duplicated per-chunk by design). Takeda is trial-thin and carries no financial
  metrics → confirms the **Novartis slice** is needed for trial-recall + market-metric
  scoring.

### Decisions / notes
- Extraction output is now a **persisted, versioned artifact** under gitignored `data/`,
  never held in memory / `/tmp` (see LEARNINGS 2026-06-09).
- Snippet fallback to chunk text is visible on mashed table rows; duplicate facts are
  present by design. Both are **Phase-2 eval measurement targets, not Stage-1 bugs**.

### Recommended next step
- Finish Stage 1: produce the **Novartis slice artifact** (only the trial-/metric-heavy
  chunks, not all 100). Then **Stage 2** — golden labeling + the eval harness (matching,
  duplicate-collapse, normalization, metrics). Do not start Stage 2 until both artifacts
  are confirmed.

---

## Phase 1 — Complete: schema → ingestion → extraction (2026-06-09)

Phase 1 is implemented, committed, and **pushed to `origin/main`**. Work continues
on branch **`phase-2-evals`** (branched from the Phase-1-complete `main`).

**This entry records Phase 1 completion** (superseded as "current state" by the Phase 2
entry above). It still supersedes the "Recommended next step" notes in the older entries
below — those predate Phase 1 and still describe token-based chunking + PDF ingestion,
both of which changed.

### Work completed (commits on `main`)
- `1fccf47` **schema** — Pydantic v2 models of the 7 entities (closed enums as
  `Literal`; open fields plain `str`); `Asset` requires ≥1 identifier.
- `767d1c9` **ingestion** — markdown loader (`data/reports/`) + section-aware
  **character-based** chunker with overlap; each `Chunk` carries provenance.
- `12db81e` **extraction** — per-chunk Gemini structured-output extraction into
  schema fact entities, grounded on `line_range` + verbatim snippet.
- Plus the setup commits (pyproject adoption, Gemini provider, markdown scope).
  Full suite: **55 tests passing**.

### Decisions that changed since the original (pre-Phase-1) handoff
- **Chunking is character-based with overlap — NOT token-based.** No tokenizer
  dependency (tiktoken is OpenAI's BPE, wrong for Gemini; exact Gemini counts are a
  remote call). See LEARNINGS 2026-06-07.
- **PDF ingestion deferred — v1 is markdown-only** (`data/reports/`); `pdfplumber`
  returns when PDF ingestion does.
- **Extraction model locked: Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite-preview`).**
  The binding constraint was free-tier **requests-per-day**, not quality (Flash-Lite
  500 RPD completes full runs; 3 Flash / 2.5 Flash were capped). Isolated behind the
  `GEMINI_MODEL` env var — swapping models is a re-run, not a code change. See
  LEARNINGS 2026-06-09.
- **Grounding: `line_range` + `snippet` are load-bearing; `section_path` is a
  decorative best-effort hint** (the corpus is a PDF-to-markdown dump that emits
  table cells as `##` headers). See LEARNINGS 2026-06-07.
- **Per-chunk extraction; duplicate assets are by design** — cross-chunk dedup /
  alias resolution is deferred to assembly (Phase 2+). See LEARNINGS 2026-06-07.

### Outstanding (for Phase 2 to measure — not pipeline bugs)
- **Flash-Lite regulatory-event and trial recall** vs the partial 2.5 Flash
  baseline — the main open question.
- Snippet sharpness on mashed table rows (designed fallback to chunk text);
  `region="other"` on ambiguous rows (model correctly declining to guess).

### Recommended next step
- **Phase 2 — eval harness + golden set.** Hand-label facts from the Takeda (and
  Novartis) reports; score extraction accuracy (exact match on closed-enum/ID
  fields, normalized/fuzzy on open free-text) and **establish the baseline before
  building retrieval**. Quantify the Flash-Lite recall gap above.

---

## Pre-Phase-1 — Ingestion scoped to markdown (2026-06-07)

Docs-only alignment before Phase 1 — no `src/` or `data/` changes.

### Decision
- **v1's canonical (and only) document format is markdown.** The corpus is the
  markdown reports already in `data/reports/` (Novartis Q1-2026 financial report,
  Takeda Q4 pipeline table). Ingestion loads markdown, cleans, and token-chunks
  with overlap.
- **PDF URL ingestion, PDF download, and PDF→markdown conversion are DEFERRED**
  to a later iteration — a deliberate scope cut, not an oversight. `pdfplumber`
  returns to the v1 tech stack when PDF ingestion does.

### Files changed
- `docs/ARCHITECTURE.md` — ingestion module description (markdown-first; PDF path
  removed), system-overview diagram input/ops, a "Deferred to a later iteration"
  note after the Modules list, and the tech-stack line (dropped `pdfplumber` from
  the v1 list, noting its return).
- `docs/HANDOFF.md` — this entry.

### Recommended next step
- Unchanged: **Phase 1 — ingestion + schema + extraction** MAY begin on explicit
  approval. Ingestion now targets markdown in `data/reports/`; start with
  `src/schema` (Pydantic v2 models of the 7 entities) as before.

---

## Pre-Phase-1 — Schema & architecture finalization (2026-06-06)

Scope and schema **locked before any Phase 1 implementation**, after a
schema-sufficiency review against the corpus (Takeda pipeline table + Novartis
Q1-2026 report). Docs only — no `src/` or `data/` changes.

### Scope decision
- **oncology-only → multi-therapeutic-area (multi-TA) pharma CI.** The corpus
  spans oncology, immunology, neuroscience, gastroenterology, rare disease,
  vaccines, cardiometabolic, etc. **Breadth comes from the corpus, not from more
  entity types.** The schema is optimized, in order, for (1) extraction
  reliability, (2) evaluation quality, (3) simplicity — explicitly over maximum
  coverage.

### Schema finalized — 7 entities
- `Document`, `SourceRef` (provenance) · `Asset` (noun) · `Program`, `Trial`,
  `RegulatoryEvent`, `MarketMetric` (dated facts, each carrying a `SourceRef`).
- **Open free-text vs closed-enum split** (the core reliability lever):
  - *Open* — suggested vocab, never coerced; out-of-vocab passes through
    verbatim (this is where multi-TA breadth lives): `therapeutic_area`,
    `indication`, `target`, `modality`, `primary_endpoint`.
  - *Closed* — small, stable, strict: `doc_type`, `region`, `Program.stage`,
    `Trial.phase`, `agency`, regulatory `action`, `MarketMetric.metric`/`basis`.
- **Key modeling decisions:** `Asset` (molecule; no `indication`) vs `Program`
  (dated asset × indication × region × stage fact) — one asset → many programs,
  the native shape of pipeline tables. `Program.stage` (lifecycle, incl.
  filed/approved/discontinued) and `Trial.phase` (a trial's phase) are separate
  axes. `Trial.nct_id` is optional (corpus trials are named by acronym, not NCT).
  Companies are **plain strings**, not an entity — the old `Competitor` entity is
  removed; company views are derived by grouping on the `company` string.
  `as_of_date` intentionally appears on **both** `SourceRef` (the document's
  snapshot date) and `Program` (the date the fact is true as of) — two distinct
  meanings, usually coincident.

### Deliberate cuts (scope, not oversight — additive later)
- **Deal / M&A entity** (e.g. the Avidity acquisition, Takeda partnership tables).
- **Rich `Company` entity** (type / country / platforms) — companies stay strings.
- **Asset + company alias auto-resolution** — aliases stored as observed;
  cross-document entity resolution deferred.
- Also deferred: biomarker/population fields, combination/regimen modeling,
  generic-biosimilar / loss-of-exclusivity tracking.
- **Why:** each protects extraction reliability + eval quality + simplicity and
  can be added later without reshaping the core.

### Eval consequence
- Extraction-accuracy scoring: **exact match** on closed-enum/ID fields,
  **normalized/fuzzy match** on the open free-text fields (`therapeutic_area`,
  `indication`, `target`, `modality`, endpoint). Recorded in `ARCHITECTURE.md` →
  evals module.

### Files changed
- `docs/ARCHITECTURE.md` — Domain-schema section rewritten to the 7-entity model;
  Project section + new "Therapeutic-area scope" note; evals scoring sentence;
  `oncology` → multi-TA scope sweep.
- `docs/ARCHITECTURE.md` — `as_of_date` temporal-provenance rationale reframed
  (document-date vs fact-date); committed separately as
  `docs: clarify as_of_date temporal-provenance rationale` (`22edc93`).
- `docs/HANDOFF.md` — this entry.
- (Also since Phase 0: the proposed venv tweak was approved and committed as
  `4e4cb62` — `python3.11 -m venv`.)

### Recommended next step
- **Phase 1 — ingestion + schema + extraction** MAY begin **on explicit approval
  — not before.** First implement `src/schema` as Pydantic v2 models of the 7
  entities (closed enums as `Literal`/`Enum`; open fields as plain `str` with the
  suggested vocab in each field's description), with pytest tests alongside.

---

## Phase 0 — Scaffold (2026-06-06)

### Work completed
- Created the full repository structure from `docs/ARCHITECTURE.md` →
  "Repository structure".
- Root `CLAUDE.md` (operating-rules source of truth): project description +
  pointer to `ARCHITECTURE.md`, stub build/test/run commands, conventions
  (Python 3.11+, Pydantic v2, full type hints, no bare excepts, small focused
  modules), security rules (never commit `.env`/keys), the do-not-replicate-v0
  list, and the **self-improvement protocol** (verbatim).
- Nested `CLAUDE.md` stubs in `ingestion`, `extraction`, `rag`, `evals`,
  `agent`, `tools` (purpose + run/test + empty gotchas). `schema/` intentionally
  has none (see decisions).
- Support files: `.gitignore`, `.env.example`, `requirements.txt`, `README.md`,
  `docs/LEARNINGS.md` (header + first entry).
- Python package stubs (`__init__.py`) per `src/` module; `.gitkeep` for
  `evals/golden/` and `tests/`.

### Architectural decisions
- **`schema/` has no nested `CLAUDE.md`** — matches `ARCHITECTURE.md`; the
  schema is a contract, not a per-module operating context.
- **`__init__.py` everywhere under `src/`** — makes each module an importable
  package and lets git track otherwise-empty dirs.
- **`data/` gitignored** — PDFs + FAISS index must never be committed; the dir
  exists locally only.
- **`.gitignore` env rule** uses `.env` + `.env.*` with `!.env.example`, so only
  the template is tracked.
- **`requirements.txt` pinned to the exact 7-package stack** from
  `ARCHITECTURE.md` (openai, faiss-cpu, rank-bm25, pydantic>=2, pdfplumber,
  httpx, pytest). Dropped `python-dotenv` (a v0 dependency, not in the target
  stack) — add back only with approval if `.env` auto-loading is wanted.

### Files changed (created)
- `CLAUDE.md`, `README.md`, `.gitignore`, `.env.example`, `requirements.txt`
- `docs/LEARNINGS.md`, `docs/HANDOFF.md`
- `src/__init__.py`
- `src/{ingestion,extraction,rag,evals,agent,tools}/CLAUDE.md`
- `src/{ingestion,schema,extraction,rag,evals,agent,tools}/__init__.py`
- `src/evals/golden/.gitkeep`, `tests/.gitkeep`

### Outstanding issues
- **Python version:** default `python3` on this machine is **3.9.6**; the
  project requires **3.11+**. Homebrew provides `python3.11` and `python3.13`
  at `/opt/homebrew/bin/` — use one of those for the venv. See `LEARNINGS.md`.
- **CLAUDE.md venv tweak — RESOLVED:** changed the venv command from
  `python3 -m venv .venv` to `python3.11 -m venv .venv` so it doesn't silently
  build a 3.9 venv. Approved and committed as `4e4cb62`.
- **Git identity — settled:** repo stays on `Praatyush <praatyushg@gmail.com>`
  (set locally for this repo); confirmed intentional.
- No code/tests yet — scaffold only. First tests land in Phase 1.

### Recommended next step
- _(SUPERSEDED — see the "Phase 1 — Complete" entry at the top: chunking shipped
  **character-based**, not token-based, and PDF ingestion was **deferred** in favour
  of markdown-only. Kept here as the historical Phase-0 record.)_
- **Phase 1 — Ingestion + schema + extraction:** implement the Pydantic v2
  domain schema (`src/schema`), the token-based chunker + PDF download/extract
  (`src/ingestion`), and structured-output extraction into the schema
  (`src/extraction`), with pytest tests alongside. Do not start until approved.
