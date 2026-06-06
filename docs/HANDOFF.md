# HANDOFF.md

Running handoff log, updated at the end of every phase: work completed,
decisions, files changed, outstanding issues, and the recommended next step.

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
