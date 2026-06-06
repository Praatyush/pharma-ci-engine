# CLAUDE.md — Operating Rules (root, source of truth)

`pharma-ci-engine` — an oncology competitive-intelligence engine that ingests
dense pharma documents + live clinical/regulatory data, extracts them into a
structured domain model, retrieves over that corpus, and answers CI questions
with **grounded, cited** output measured by an offline eval harness.

**Design source of truth: `docs/ARCHITECTURE.md`.** That file owns the system
design (modules, data flow, schema, build order). This file owns the *how* —
run/debug commands, conventions, and the self-improvement protocol. Keep them
separate; do not duplicate the architecture here.

Claude Code reads this root file automatically, plus the nearest nested
`CLAUDE.md` when working inside a `src/` module. Put module-specific gotchas in
the nested file, not here.

## Commands

> Stubs — fill in as each phase lands. Update the relevant line when a command
> becomes real.

```bash
# Environment (Python 3.11+)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in real keys locally (never commit .env)

# Test (pytest)
pytest                          # full suite
pytest tests/ -k <expr> -q      # focused run

# Run — added per phase as modules become runnable
# (ingestion / extraction / rag / agent entry points TBD)
```

## Conventions

- **Python 3.11+.** Full type hints on all public functions; prefer explicit
  types over `Any`.
- **Pydantic v2** for the domain schema and structured-output extraction
  (`model_validate`, `model_dump`, `Field`; not v1 `.parse_obj` / `.dict`).
- **Small, focused modules** matching the `src/` layout in `ARCHITECTURE.md`.
  One responsibility per module; no god-files.
- **No bare `except:`.** Catch specific exceptions; never swallow errors
  silently. Let unexpected exceptions propagate.
- Keep model names (LLM + embeddings) **configurable**, not hardcoded.
- Write **pytest tests alongside code** in `tests/`, mirroring the `src/` path.

## Security

- **NEVER commit `.env` or API keys.** Only `.env.example` (placeholders) is
  tracked. `.env` is gitignored — keep it that way.
- **Never hardcode secrets** in source. Read them from the environment.
- `data/` is gitignored: sample PDFs and the FAISS index must never be
  committed.

## Do NOT replicate v0 (`docs/V0_ARCHITECTURE.md` is context only)

The previous prototype was a generic financial summarizer. We are migrating
away from all of it. Do not reintroduce:

- map-reduce summarization (re-reading whole documents per run)
- financial output buckets / generic-financial framing
- tkinter / any GUI
- PyInstaller / desktop-app packaging
- freeform `.txt` output

This system is CLI / library-first, retrieval-based, structured, evaluated, and
domain-pivoted to **oncology clinical-lifecycle intelligence**.

## SELF-IMPROVEMENT PROTOCOL

When you fix a non-obvious bug or discover a project convention or gotcha:

1. Append a dated entry to `docs/LEARNINGS.md` (format: `## YYYY-MM-DD — <title>`,
   then **What** / **Why** / **Fix**).
2. If it is a durable convention, **PROPOSE** an edit to the nearest `CLAUDE.md`
   (root or module) — show the diff and ask before applying. Do **NOT** silently
   rewrite core instructions.
3. Keep `CLAUDE.md` lean: prune and merge rather than appending forever.

## Working rules

- Build in **phases**; stop for review after each (see `ARCHITECTURE.md` →
  "Build order"). Do not run end-to-end.
- **Ask before adding any dependency** not already in `requirements.txt`.
- Commit per phase with clear messages; never commit secrets.
- At the end of every phase, create/update `docs/HANDOFF.md` (work completed,
  decisions, files changed, outstanding issues, recommended next step).
