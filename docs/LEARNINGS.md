# LEARNINGS — bug fixes, conventions, and gotchas (append-only; newest first)

## 2026-06-11 — T (containment threshold), third appearance: coarse units reproduce bimodality

**What:** The containment threshold **T** has now resisted calibration **three** times, and the
retrieval-plan design (`docs/RETRIEVAL_PLAN.md` §A.6) finally names the mechanism. (1) Golden lock:
extraction-provenance `line_range`s bias containment to ≈1.0. (2) Labeling pass: containment was
bimodal (1.0/0.0) because the stand-in unit was *the chunk containing the span*. (3) Retrieval
design: **even with REAL ranked retrieval, the locked 1500/200 chunk units keep containment
bimodal** — so T still cannot be richly calibrated at chunk grain.

**Why (the non-obvious part):** the earlier framing blamed the ≈1.0 bias on the *labeler* choosing
the containing chunk as the stand-in. That is only half the story. The deeper cause is a
**granularity mismatch**: golden spans are short and semantic (1–14 lines), retrieval chunks are
coarse (~80 lines), and the chunks are non-overlapping outside a 200-char seam. So a short span
sits **entirely inside one chunk** (containment 1.0 if that chunk is retrieved) and overlaps a
**neighbor by 0 lines** (containment 0.0) — there is no fractional middle for T to threshold.
**Swapping the labeler's stand-in for a real retriever does NOT, by itself, produce sub-1.0
containment.** Fractional containment requires retrieval units **comparable to or finer than the
spans**, which coarse chunks are not.

**Fix / rule:** do **not** pre-emptively re-chunk to "fix" T. Reuse 1500/200 for Stage A (locked),
make T-calibration an explicit Stage-A sub-task that emits the **distribution** of max-containment
over retrieved top-k, and **decide at Gate A with data**: pin T if a usable fractional distribution
exists; else either adopt a finer retrieval `ChunkConfig` (a Gate-A lever, not a now-change) **or
report that T is structurally inert at chunk grain** and pin it only via the long-span / aggregate /
comparison cases. Same reasoned-deferral discipline as the original T deferral and the RRF
α-avoidance — a rank-/threshold-free design wherever the golden can't calibrate the knob. T is now
**deferred-with-a-understood-mechanism**, not deferred-by-ignorance.

## 2026-06-11 — Retrieval relevance policy: gate-then-pass, and the tripwire stayed dry

**What:** The Phase-3 retrieval golden was built by **discovering the policy's holes before
trusting it**, not by labeling straight through. Two **gates** labeled one query each
end-to-end to break the policy on purpose: **Q3** (mashed oveporexton row) broke v0 §5 — it
keyed resolution_limited on *surface-token* line-uniqueness, which the positional region↔date
binding defeated → rewrote §5 to key on **answer-bearing-span isolation**, with a *sibling* =
"a competing answer to the **same query slot**" (a different-indication co-located fact is NOT
a sibling), span-level. **Q5** (IgAN cross-doc) broke v1 §3 — one-fact-one-span couldn't
represent a company with **multiple assets at different stages** → rewrote §3 comparison to
**two coverage scores** (presence AND∘OR∘OR + attribute AND∘OR). Then a full **labeling pass**
with a **tripwire**: on the first *new* relational query of each shape, stop and ask "did §3 v2
hold?"

**Why it matters:** a break at the tripwire is a *success of the gating process*, surfaced
loudly, not patched silently. The **aggregate** construct (recall-over-row-set) was validated
on **Q4** (CV pipeline) and **HELD** — the tripwire **stayed dry**, so the pass completed.

**Fix / rule:** policy v2 is **locked** and embedded in `src/evals/golden/retrieval.golden.json`
(`policy_v2` + `validation_history`). Construct selection is **closed-and-query-defined
(set-of-singles) vs open-and-corpus-defined (aggregate)** — a literal source value that *sounds*
categorical (Q1 "Multiple Indications") does NOT make a query an aggregate. Authorship rule:
golden spans come from **reading source**, never extraction output.

## 2026-06-11 — Comparison construct is validated-on-motivating-case-only (zero-asset untested)

**What:** The §3 v2 **comparison** construct (presence-coverage + attribute-coverage, two scores
never collapsed) has been exercised on **exactly one** query — its motivating case **Q5** (IgAN).
There is **no second, fresh comparison** in the seed set, so it is **NOT independently
validated**.

**Why:** In particular the **zero-qualifying-asset case is untested** — a comparison where one
compared entity has *no* qualifying asset, so presence-coverage must score that side **0** (e.g.
"which of A and B have a CAR-T for lupus" when only one does). Q5 had both sides present
(Takeda 1 asset, Novartis 3), so the 0-branch of `AND(entities)` never executed.

**Fix / rule:** treat this as a **known limitation, not settled validation** (recorded in the
golden's `3_construct_comparison_STATUS`). Re-evaluate — and revise the construct if needed — on
the **first future comparison query that exposes a deficiency**. Do not assume the two-score
construct generalizes until a zero-asset (and a second multi-asset) instance has run.

## 2026-06-11 — Two distinct entity-leg blindnesses; the chunk leg is the only backbone

**What:** The retrieval golden surfaced **two different reasons** the entity (extracted-fact)
retrieval leg cannot answer a real CI query — both rescued **only** by the chunk (text)
retrieval leg:

- **Blindness by UN-EXTRACTION.** Novartis's only *approved, marketed* IgAN asset
  **Vanrafia (atrasentan)** lives at `q1-2026-interim-financial-report-en` **L443–445**, an
  **un-extracted** chunk (it's filed under the CVRM franchise; Novartis extracts only 12 of 100
  chunks). The entity leg has nothing indexed there. (Q5; the asset the seed sketch itself
  missed.)
- **Blindness by MISCLASSIFICATION.** The Takeda plasma reg-events (`qr2025_q4_Pipeline_table_en`
  **L555–581** + progress rows) are in **extracted** chunks, but Flash-Lite emits the
  "Approved/Filed (date)" cells as a Program **`stage`**, not a `RegulatoryEvent` — so the entity
  leg returns the **wrong entity type** even though the text is indexed. (Q1; the plasma-recall
  finding from Phase 2, now reframed for retrieval.)

**Why it matters:** these are the concrete, portfolio-valuable justifications for the locked
Phase-3 design (chunk retrieval = baseline + reachability backbone; entity retrieval = a measured
layer on top). Un-extraction and misclassification are **different** failure modes and must be
reported as **different** slices — un-extracted spans are tagged `un-extracted` (§6); misclassified
ones are `extracted` but flagged in the query note.

**Fix / rule:** the retrieval golden keys every span `(doc_id, line_range)` and tags each
`extracted | un-extracted | mixed`; reporting is **always sliced** — never merge a coverage number
across the two (a merged "Novartis 2/3" would hide that the headline answer is entity-leg-unreachable).

## 2026-06-11 — Retrieval containment threshold T is DEFERRED (reasoned), not chosen

**What:** The containment threshold **T = 0.5** (§2: a unit HITS a golden span when ≥ T of the
span's lines fall inside it) is **provisional and explicitly un-calibrated**. Neither the two
gates nor the labeling pass produced **any** evidence to tune it.

**Why (this is the subtle part, not an oversight):** the labeling used **extraction-provenance
`line_range`s as stand-in retrieved units**, and a fact's authored golden span sits **inside the
very chunk that extracted it** — so containment comes out **≈1.0 by construction**. Across all 9
scored queries containment was **bimodal (1.0 / 0.0)** and **no span straddled a unit boundary**,
so T could be anything in (0,1] and every verdict is identical. The stand-in method **cannot
falsify T**.

**Fix / rule — deferred decision with a stated trigger:** do **NOT** tune T from labeling.
**Calibrate T against the first real retrieval index**, where a retriever returns units with
*independent* boundaries and **sub-T containment can actually occur** (long answer spans, spans
straddling chunk edges). Until then T=0.5 stands as a placeholder, and §4 `borderline_containment`
is expected to stay inert (it did this pass). Recorded in the golden's `t_calibration`.

## 2026-06-10 — restatement FP subcategory: cross-chunk duplicates of captured facts

The third "not-a-clean-FP" subcategory (after `key_incomplete` and `indication_verbose`) — the
FP-decomposition discipline applied once more. Because the reg census labels restatement chunks
(Takeda progress rows 14-16 restate the main table 8-12), the model's cross-chunk duplicate
extractions with **inconsistent regions** (`tak-279 HS` = `Global` in one chunk, region-`-` in
another) don't collapse, and the extras land as FP. `matching._duplicates_matched` reclassifies
an FP that duplicates an already-MATCHED fact (same asset + collapsed-stage + compatible/contained
indication; region differs) into a `restatement` subcategory: excluded from clean FP so
**precision-on-distinct-facts** is reported cleanly (programs 0.78 raw → **0.88** distinct + 10
restatement), but **NOT** merged away in collapse — merging would erase the real
model-consistency finding. It is BOTH a genuine signal AND a census-composition artifact:
decompose-and-report, never merge-away.

## 2026-06-10 — indication_verbose: classify model over-specification, don't match it

**What:** The model writes a program's indication as the disease PLUS population/setting
("Pediatric on-demand and surgery treatment of von Willebrand disease"); golden (indication =
disease only) is "von Willebrand disease". The fuzzy key doesn't bridge clean-vs-verbose.

**Why NOT containment-match:** an asymmetric subset *match* would silently produce FALSE TPs —
"von Willebrand disease" ⊆ "**acquired** von Willebrand disease" (congenital vs acquired = a
different condition) would match and inflate recall invisibly. Same weak-alias-chaining failure
as the IVIG over-merge and "Total".

**Fix — classify, don't match.** A clean FP that agrees with a still-MISSED golden on every key
field except indication, where the golden disease tokens (≥2 significant) ⊆ the predicted
indication + extras, is reclassified to an `indication_verbose` FP subcategory (mirrors
`key_incomplete`): the predicted leaves clean-FP (precision not charged a phantom), the golden
**STAYS a miss** (recall never inflated — a narrowing case like "acquired X" is *visibly*
bucketed for review, never a silent TP). Reported separately with both indication strings. The
≥2-significant-token floor means single-token diseases ("Hemophilia A" → just "hemophilia")
aren't auto-classified — conservative by design.

**The real finding it surfaces (schema gap):** `Program` has `line_of_therapy`/`formulation`
but **no population/setting field**, so the model has nowhere to put "pediatric / on-demand /
surgery" except the indication string. That's a **schema-v2 / Phase-2-retrospective** lesson —
NOT a mid-census change to the frozen schema. Named, not acted on.

## 2026-06-10 — Two key-normalizations: sub-phase collapse + region-indeterminate

Surfaced by the Takeda pipeline table (census batch 1). One reusable pattern names both:
**collapse a sub-distinction the source makes but the key shouldn't gate on.**

- **Sub-phase collapse (the stage analog of the agency PMDA==MHLW fold).** Source writes
  `P-II (b)`; the model writes `P2`. `P2b` IS a Phase 2, so gating the key on the sub-letter
  manufactures false misses. `matching.collapse_phase` strips the sub-phase letter
  (P2a/P2b→P2, P3a/P3b→P3, 2a/2b→2; leaves P1/2, preclinical, filed, …) for the **key** in
  both program and trial matching. Golden keeps the precise sub-phase; sub-phase is a scored
  attribute. Generalized (not a P2a/P2b special-case) so a future `P3b` doesn't reopen this.
- **Region-indeterminate (`region=null`).** A "-" in the region column = the source states
  NO region. Verified there is **no legend** defining "-" (the glossary defines CN/EU/JP/U.S.
  and spells out "Global" as a word). Labeling it `Global` would manufacture a key value from
  absence — and would assert on the golden side exactly what grounding penalizes on the
  predicted side (11% regions inferred-not-stated). So `GoldenProgram.region` is nullable;
  null drops region from the key (`program_matches`: `g.region is None or p.region==g.region`)
  and the program is still scored on asset+indication+stage. Same discipline as the chunk-29
  region-inferred exclusions. Affected 10 programs in census chunks 8-9.

**Labeling guard (bitten twice — IT-formulation, then "Pediatric" on MLN0002):** `indication`
= DISEASE ONLY; population/formulation/dosing/line-of-therapy are separate fields, never folded
into the indication string. Recorded in `src/evals/CLAUDE.md` policy (e).

## 2026-06-10 — Grounding full-run findings + the chunk-granularity caveat

Full grounding run over all **307 predicted facts** (`grounding.py`, commit `1849a1d`):

- **Headline provenance (PRECISE, reportable):** the load-bearing tokens ground high and are NOT
  affected by chunk granularity (they key on locally-unique, molecule-specific tokens): **asset
  98%, action 100%, value 100%, indication 97%**. Predicted facts are genuinely cited to lines
  that contain the molecule / regulatory verb / number / indication.
- **CHUNK-GRANULARITY CAVEAT (stated property of the layer):** grounding checks token presence
  *anywhere* in the cited `line_range`, so for dense chunks (Takeda L25-84 = 30 programs in one
  range) region/stage both **over-credit** (a neighbor row's region rescues a wrong fact) and
  **over-fail** (`Global` in a chunk that names specific regions). Therefore **region (62%) and
  stage (53%) are DIRECTIONAL indicators of a real weakness, NOT precise rates** — this caveat
  travels with those two numbers wherever reported. We are deliberately **not** building a
  row-level fix: sub-splitting line_ranges fights the chunk-based provenance model, and the
  finding holds whether it's 62% or 58%. Measure-and-caveat.
- **Region inference = predicted-side mirror of golden policy 3 (finding, not a bug):** 11% of
  region tokens are `Global` with NO region word in the source. The two harness halves agree
  from opposite directions (golden excludes region-inferred facts; grounding flags them).
- **Stage failure split:** 40 `map_gap` / 69 `real_failure` → ~37% of stage "failures" are
  fixable token-map coverage (Novartis bare-number phase encoding), not extraction faults.
- **Hard provenance error rate ~0.3%:** of 7 `asset` real_failures, **6 are market-metric
  subjects** (value grounds; the subject word isn't on the cited line — the company
  self-reference finding), and **1 is a genuine wrong-line citation** (177Lu-NeoB cited to a
  Duchenne MD row). 1 confirmed wrong-line provenance error in 307 facts — logged, not chased.

## 2026-06-10 — Grounding: region-inferred and map-gap are distinct from real failures

`grounding.py` checks whether a predicted fact's cited `line_range` contains its salient tokens
(closed enums via a reverse surface-form map: source "Approved"/"PhIII"/"Japan" ↔ enum
`approval`/`3`/`JP`). A missing token has THREE distinct causes, reported as separate categories
so a low grounding rate is not misread:

- **real_failure** — genuinely absent (wrong line cited / fact not in the text): an
  extraction-provenance fault.
- **map_gap** — a recognizable surface IS present but the map doesn't bridge it (Novartis encodes
  phase as a bare "3", which the map deliberately won't match — ambiguous with years): a fixable
  token-map gap, NOT an extraction fault. So grounding pass-rate is **partly a map-coverage
  measure**, not purely an extraction signal.
- **inferred** (region only) — NO region word is in the cited text; the model asserted a region
  the source never states. This is the **predicted-side mirror of golden policy 3** (we excluded
  region-inferred programs from golden because the source didn't support the key). Grounding is
  the layer that catches "the model asserts regions the text doesn't state" — so region grounding
  is its own prominent number; a low rate is a FINDING.

`line_range` is load-bearing; `snippet` is decorative and `snippet_fallback` (mashed-row chunk
fallback) is EXPECTED, reported separately. **Also:** surface matching must be token-bounded —
substring matching had the region surface `us` grounding inside "lupus"/"erythematosus"; fixed
with `grounding._contains` (non-alphanumeric boundaries).

## 2026-06-10 — therapeutic_area is reported descriptively, NOT scored for accuracy

**What:** `metrics.py` first scored `therapeutic_area` as a matched-program attribute (5
"errors" like von Willebrand disease `hematology` vs `rare_disease`).

**Why that's wrong:** `therapeutic_area` is OPEN free-text **by locked design** — we deliberately
did not enumerate it because there is no canonical TA taxonomy. Scoring it for accuracy against a
golden label smuggles a taxonomy back in (the labeler's bucket becomes "correct"), contradicting
the reason the field is open. `indication` is different — "IgA nephropathy" is a fact with real
ground truth, so it stays a fuzzy **key**.

**Fix:** `therapeutic_area` is EXCLUDED from scored attribute-accuracy and emitted as a
descriptive `ta_disagreements` list (predicted bucket vs golden bucket + line_range), never an
error count. Aggregate P/R/F1 is unaffected (TA was never in TP/FP/FN). The same taxonomy-free
property applies to `modality` / `target` / `primary_endpoint` — also open, also not scored for
accuracy. (Aside, from the same review: `metrics._locate` is display/provenance only and is not
in the scoring path — the program TP 32→31 move was union cross-chunk dedup, not `_locate`.)

## 2026-06-10 — Golden labeling policies: multi-region, under-specified, ambiguous-region

All from one principle: golden encodes what the SOURCE supports at the SCHEMA's grain — never
tuned to the model's output, never inventing a key value from labeler uncertainty.

1. **Multi-region actions are SPLIT.** `region` is in the RegulatoryEvent key, so "US, EU, JP
   & CN submissions" is FOUR `filed` events. The model emitting one is a real
   under-decomposition miss, not a reason to collapse golden. `metrics.py` also reports a
   region-collapsed recall cut so one 4-region sentence (4/13 of the standalone denominator)
   can't dominate the headline.
2. **Key-incomplete ≠ false positive.** A predicted fact whose open-text KEY field is a null
   sentinel (a designation with `indication="not specified"`) is **under-specified**, not
   hallucinated: keep the golden FN (no indication = no captured fact), but score the predicted
   side as a distinct `key_incomplete` outcome (matching.is_key_incomplete /
   normalize.is_null_sentinel), NOT a clean FP — precision must not eat a phantom FP. Do NOT
   demote indication to an attribute to fix this; indication has real disambiguating power
   (IgAN vs SLE), and demoting it would tune the key to the model. Finding: Flash-Lite extracts
   regulatory designations but routinely drops the indication.
3. **Ambiguous region: don't manufacture a key.** Real model errors stay errors (the source
   shows Pluvicto's EU application was WITHDRAWN; a model "EU approved" is a genuine FP). But
   where the source gives region only by mashed-column position (not prose), EXCLUDE the fact
   rather than guess — `region="other"` is a substantive enum ("outside the named set"), NOT an
   unknown-sentinel, so using it that way manufactures fake matches/penalties. Same discipline
   as policy (c): no source support for a key field → don't invent one. (Applied: 3
   region-inferred chunk-29 programs excluded; molecules kept as assets, prose-explicit
   reg-events kept.)

Effect on the 5-chunk batch: reg-event **precision 0.67→1.00** (3 designation FPs → KI),
**recall 0.26** (standalone 0.23 / progress-row 0.30); programs R 0.65→0.70. Clean findings
unchanged: Takeda chunk-12 reg-events **0/7** (table status cells extracted as program stages,
not RegulatoryEvents) and the IVIG over-merge (3 distinct plasma molecules → 1 predicted
cluster).

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
