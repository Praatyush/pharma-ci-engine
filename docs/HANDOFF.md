# HANDOFF.md

Running handoff log, updated at the end of every phase: work completed,
decisions, files changed, outstanding issues, and the recommended next step.

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
- **Proposed CLAUDE.md tweak (awaiting approval):** change the venv command from
  `python3 -m venv .venv` to `python3.11 -m venv .venv` so it doesn't silently
  build a 3.9 venv. Not applied yet (self-improvement protocol: propose, don't
  silently rewrite core instructions).
- **Git identity** was unset globally; set **locally** for this repo to
  `Praatyush <praatyushg@gmail.com>`. Change if that's not the intended author.
- No code/tests yet — scaffold only. First tests land in Phase 1.

### Recommended next step
- **Phase 1 — Ingestion + schema + extraction:** implement the Pydantic v2
  domain schema (`src/schema`), the token-based chunker + PDF download/extract
  (`src/ingestion`), and structured-output extraction into the schema
  (`src/extraction`), with pytest tests alongside. Do not start until approved.
