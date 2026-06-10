# LEARNINGS — bug fixes, conventions, and gotchas (append-only; newest first)

## 2026-06-10 — Own-company metrics get a generic subject ("Company"), not the name

**What:** On Novartis chunk 32 the net-sales `MarketMetric` matched on value/period/geography
but FAILED on the `subject` key — predicted `subject="Company"`, golden `"Novartis"` — scoring
0 TP / 1 FP / 1 FN despite identical numbers.

**Why:** The consolidated income statement does not repeat the company name per line ("Net
sales to third parties … 13 113"), so Flash-Lite labels the company's own consolidated figures
with a generic subject ("Company"). This is the company-level analog of the period demotion: a
discriminator stated once globally, not per row.

**Fix:** `normalize.fold_self_reference(subject, source_company)` maps generic self-references
(`Company` / `the Company` / `the Group` / `<company>` / `<company> group`) to the document's
`source_company` by **exact canonical match**, applied to predicted AND golden subjects before
collapse/match. After the fix chunk-32's metric flips to **1 TP / 0 FP / 0 FN**. Deliberately
**excludes "Total"** — an aggregation marker that can denote a segment/summed subject, not the
company; folding it would risk the weak-alias chaining seen in the asset over-merge. (Confirmed
against the artifact: "Total" never appears as a subject; product groups like "Sandostatin
Group" do and must NOT fold.) `metrics.py` must apply this fold — the matching predicate has no
document context.

**Also (corpus fact):** there are **zero NCT IDs** in either source document (0 predicted
trials carry one) — trials are acronym-named. The trial-key `nct_id` tier is unexercised by
real data (unit-tests only); matching falls through to `trial_name` then assets+indication+phase.

## 2026-06-10 — Scope predictions to labeled chunks BEFORE collapsing (not after)

**What:** First end-to-end scoring of one labeled chunk (Takeda chunk 14) produced **false
FNs** — golden programs/reg-events that Flash-Lite *did* extract were scored as misses
(TAK-961, TAK-861).

**Why:** The harness collapsed predictions **document-wide first**, then scoped to the
labeled chunk by the collapsed representative's `source_ref.line_range`. `collapse()` keeps
the **first** emission's `source_ref`, so a fact extracted in several chunks is attributed
to whichever chunk came first. TAK-861 (narcolepsy, filed) and TAK-961 appear in BOTH the
chunk-9 regulatory table and the chunk-14 progress table; their representatives were stamped
chunk 9, so scoping to chunk 14 dropped them. Confirmed: chunk 14's RAW extraction had all
4 programs + 3 reg-events.

**Fix / rule (for `metrics.py`):** Scope **raw** predictions to the **union of labeled chunk
indices**, collapse **once within that union**, and match against the **union of golden
labels**. Do **NOT** collapse-then-scope, and do **NOT** sum per-chunk scores — a fact in two
labeled chunks (TAK-861 in 9 and 14) would be **double-counted**, measuring per-*mention*
recall instead of per-*fact* recall. The document-wide `collapse()` stays (correct for the
dedup-count report and the shared asset index, just not for chunk-scoped fact selection).
Asset P/R is separately **document-level** (assets carry no `source_ref`, can't be
chunk-scoped) and is gated on the document's full asset set being labeled.

## 2026-06-10 — Asset clustering can transitively over-merge on shared weak identifiers

**What:** The eval duplicate-collapse clusters assets by **shared-identifier union-find**
(the same molecule appears as `ianalumab` and `VAY736`, etc.). On Takeda this chained
**9 distinct IVIG programs into one cluster** (`10-ivig, deqsiga, gammagard-liquid,
glovenin-i, tak-339, tak-880, tak-961, …`).

**Why:** Extraction **over-applied non-unique identifiers across distinct dev codes** — it
put brand `GAMMAGARD LIQUID` on *both* `TAK-880` and `TAK-339`, and alias `10% IVIG` on
`TAK-339` / `TAK-880` / `TAK-961`. Union-find then transitively merges any assets sharing a
slug, so these weak shared strings chain otherwise-distinct molecules into one mega-cluster.
It is therefore *both* an extraction-quality issue (shared brand/alias reused) and an
amplification by the merge-on-any-shared-identifier rule. The correct merges still work
(`Adzynma ≡ ADAMTS13 ≡ TAK-755`, `Fabhalta ≡ iptacopan ≡ LNP023`, `Leqvio ≡ inclisiran`).

**Fix / decision (v1):** **Keep the simple merge-on-any-shared-identifier rule** and let the
golden set **quantify the impact before adding mitigation**. The over-merge is localized to
Takeda's IVIG codes, and the considered mitigations carry their own under-merge risks:
*Option B* (bridge only on strong ids — generic_name + dev codes) would under-merge
brand-only references (a "Fabhalta"-only mention would not join the iptacopan cluster);
*Option C* (refuse to merge two clusters that each already hold a distinct dev code) adds
clustering logic. Both **deferred** pending golden-set evidence. Revisit if golden shows
asset precision/recall is materially distorted by chained clusters.

## 2026-06-09 — Extraction output must be persisted (the prior run was lost)

**What:** The "34/34 Flash-Lite run completed" recorded in HANDOFF left **no artifact on
disk** — a Phase-2 scan of the repo, `/tmp`, and `$HOME` turned up no pickle/JSON. The
output had lived only in memory (any `/tmp` scratch was ephemeral / cleared), so it could
not be scored without re-running and re-burning free-tier quota.

**Why:** `extract_document` returned an in-memory `ExtractionResult`; nothing serialized
it. `/tmp` is not durable, and the result was never written under the repo's gitignored
`data/`.

**Fix:** Added `src/extraction/persistence.py` (`save_extraction` / `load_extraction`: a
versioned `schema_version` + `meta` + `counts` + `result` JSON that round-trips an
`ExtractionResult` losslessly) and a CLI `python -m src.extraction.run --report <name>`
that runs paced extraction and writes the artifact to `data/eval/extractions/` (gitignored
via `data/`). That persisted artifact is the **fixed input** the eval harness scores
against — produced once, never re-extracted just to iterate on scoring. **Rule:** any
expensive LLM pass downstream work depends on must be persisted to `data/` at
produce-time, not held in memory or `/tmp`.

## 2026-06-09 — Extraction model decision: Gemini 3.1 Flash-Lite + pacing

**Model decision:** Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite-preview`) is the v1
extraction model. The binding constraint was **free-tier requests-per-day, not model
quality**: in AI Studio for this project, Gemini 3 Flash showed **20 RPD** (cannot finish
a single 34-chunk document, let alone the ~134-call full corpus), and 2.5 Flash was
similarly capped; only **Flash-Lite at 500 RPD** can complete full runs with headroom to
iterate. The model is isolated behind the `GEMINI_MODEL` env var, so swapping to a
stronger model later is a **re-run, not a code change**. Extraction quality — notably the
**regulatory-event and trial recall gap** observed vs the partial 2.5 Flash baseline —
remains to be measured against the Phase 2 golden set before retrieval is built on this
corpus.

**Pacing:** the full 34-chunk Flash-Lite run completed **34/34 with zero 429/503 backoff**
at a fixed **4.5s inter-call delay** (~13 req/min, under the 15 RPM cap). Unpaced runs
wall on the free tier (the 2.5 Flash baseline lost chunks 23–33 to 429); **proactive
pacing is required**, not reactive backoff.

**Open Phase 2 eval targets (not pipeline bugs):** (1) regulatory-event / trial recall on
Flash-Lite; (2) snippet sharpness on mashed table rows (the designed fallback to chunk
text when the model's `evidence` is not a verbatim substring); (3) `region="other"` on
ambiguous rows (the model correctly declining to guess).

## 2026-06-07 — Per-chunk extraction: duplicate assets are by design

**What:** Extraction is per-chunk (one Gemini call per `Chunk`). An asset that
appears in N chunks is therefore emitted as N separate `Asset` objects, and facts
reference assets by a slug of the name/code as written. Duplicate assets (and
within-chunk-only `asset_id` linking) in extraction output are **expected, not a
bug**.

**Why:** Per-chunk is what makes `SourceRef` grounding exact — each fact carries
the originating chunk's `line_range` + verbatim `snippet`. Per-document assembly
would force the model to invent locators. Cross-chunk dedup / alias resolution is
already an explicitly DEFERRED concern in `ARCHITECTURE.md`.

**Fix / rule:** Treat extraction output as raw, pre-assembly facts. Dedup +
cross-chunk asset/alias resolution belongs to assembly (Phase 2+), not extraction.

**Also:** `Program.as_of_date` is required by the schema but the source states its
snapshot date once globally (e.g. Takeda "as of May 13, 2026"), not per row — so
the document snapshot date is **caller-supplied** in v1 (`extract_document(...,
as_of_date=...)`); auto-extraction from body text is deferred.

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
