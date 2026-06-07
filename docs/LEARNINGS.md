# LEARNINGS — bug fixes, conventions, and gotchas (append-only; newest first)

## 2026-06-07 — section_path breadcrumbs are unreliable on this corpus

**What:** Both v1 source reports are PDF-to-markdown dumps that emit table cells
as ATX `##` headers — Takeda has 433, Novartis 1471 — most of them noise or
fragments (a "Small molecule" cell wrapped across two lines becomes `## Small`
then `molecule`; financial values become `## 13 233`, `## -1`; there are also
`## ®`, `## USD`). So a chunk's `section_path` (header breadcrumb) is frequently
meaningless on this corpus.

**Why:** The conversion had no semantic header hierarchy to preserve — everything
above body text was promoted to `##`. Neither file has a `#` H1 or markdown pipe
tables.

**Fix / rule:** `line_range` + `snippet` are the **load-bearing provenance** —
always exact (a verbatim slice of `LoadedReport.lines`). Treat `section_path` as a
best-effort hint only. **Extraction must NOT rely on `section_path` to infer
document structure**; read the chunk text (and, if needed, neighboring lines via
`line_range`) instead. Section *packing* is what keeps the chunk count sane
(Takeda 34, Novartis 100) despite the header noise.

**Note:** "GSK" in the Takeda body text (e.g. "*1 Partnership with GSK") is a
**real partnership mention** in the content — distinct from, and unrelated to, the
phantom "GSK source document" that was correctly removed from the docs earlier
(commit `a7e7164`). Do not re-conflate them.

## 2026-06-07 — Char-based chunking (not token-based) for v1 ingestion

**What:** v1 ingestion chunks markdown by **characters with overlap**, not tokens.
`ARCHITECTURE.md`'s "token-based chunk" wording is updated to char-based-with-overlap.

**Why:** The provider is Gemini. `tiktoken` is OpenAI's BPE — its counts don't match
Gemini's tokenizer, so it would only be a proxy (no better than chars÷4) while adding
a dependency and a first-use vocab download. The only *exact* Gemini count is the
SDK's `count_tokens`, a server-side call — the wrong tool for a chunking inner loop
(latency, quota). For markdown v1, chunk-size precision isn't load-bearing: chunks
only need stable, comfortably-bounded windows for extraction and (Phase 3) retrieval.

**Fix:** Character-based chunking with overlap (stdlib only), keeping chunk size +
overlap configurable, with a configurable `chars_per_token` (~4) if a budget ever
needs to be expressed in approximate tokens. No tokenizer dependency added. Revisit
a real Gemini/Gemma tokenizer only if Phase 2 evals show chunk-size sensitivity.

## 2026-06-06 — Use Python 3.11+ explicitly; system `python3` may be 3.9

**What:** The project requires Python 3.11+, but the macOS system `python3` can
be older (3.9.6 on this machine). Creating a venv with the bare `python3` would
silently produce a 3.9 environment.

**Why:** macOS ships an older Apple Python as the default `python3`; newer
interpreters live elsewhere (e.g. Homebrew at `/opt/homebrew/bin/python3.11`,
`python3.13`).

**Fix:** Create the venv with an explicit 3.11+ interpreter
(`python3.11 -m venv .venv` or `python3.13 -m venv .venv`) and verify with
`python --version` *inside* the activated venv before installing requirements.
