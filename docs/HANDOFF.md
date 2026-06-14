# HANDOFF.md

Running handoff log, updated at the end of every phase: work completed,
decisions, files changed, outstanding issues, and the recommended next step.

---

## Phase 4C — SUBSTANTIVELY COMPLETE: live-tool escalation built, committed, live-validated; HTTP layer under regression (2026-06-13)

**AUTHORITATIVE STATUS:** **Phase 4C (live tools) is SUBSTANTIVELY COMPLETE — the live-tool escalation
capability is built, committed, live-validated on the clean entity-absence case, with the working HTTP
layer under a committed regression suite.** On branch `phase-4-agent`, **local-only — NOT yet merged or
pushed.** The merge + push to `main` is **deferred to a later deliberate step** (per the original plan;
the whole phase has been local-only).

- **What was built/committed (the full 4C chain, in order):** the 4C contract docs (`73a0f8d`) + the
  `httpx` dependency gate (`3a6d740`); the two API clients — CT.gov `clinicaltrials_lookup` (`fbb3d66`)
  and openFDA `fda_lookup` (`7a8efe4`); the recorded fixtures (`1ed7221`); the types/seam plumbing +
  `gap_kind` dispatch (`c55aaf2`, `3cc66f0`); the scorer record-identity faithfulness + value-layer
  atoms (`a209ddd`, `50ae2c3`); the live golden (`d40fdba`); the live-eval findings doc (`9ce150c`);
  the **§6.5 injected-transport seam** (`b5d1a61`); and the **MockTransport client test suite**
  (`305d1bf`). **Suite at 144** (135 pre-4C + 9 new client tests).
- **What works (live-validated, real Gemini temp 0):** **`regulatory_status` escalation END-TO-END**
  (L2 — "is pitolisant approved?" → `fda_lookup` → `openfda:NDA211150` record-identity citation →
  scored **1.0**) + the **corpus control** (Q2 answers fazirsiran Phase III from the corpus, calls NO
  tool, scored 1.0). The live-tool capability is **demonstrated on the clean entity-absence case**; the
  corpus-first invariant holds (dispatch is discerning, not trigger-happy).
- **Known limitation (characterized, not a bug):** **`trial_status` escalation for
  attribute-absence-with-present-subject (L1)** — the **4A I3 attribute-vs-subject seam** (subject
  present, requested fact absent → ASSESS judges sufficient and never escalates). **Not prompt-fixable**
  (a narrow ATTRIBUTE CHECK produced a **byte-identical** verdict; reverted, committed prompt
  unchanged); structural fix **deferred, out of scope**. See `LEARNINGS.md` (2026-06-13).
- **Coverage / robustness:** the **HTTP client layer is covered by the committed MockTransport suite**
  (keyless / networkless, §6.5 — request shape + parsed records + the current raise/propagate failure
  behavior). The **§9.3 failure-handling wrapper is deliberately DEFERRED / out of 4C scope** — the
  clients raise/propagate by design; the no-match behavior (incl. the confirmed openFDA
  404-on-no-match) is **characterized, not built**.
- **Golden:** `agent.golden.live.json` left as authored — L1's entry expresses the **intended**
  behavior; the measured L1 failure is recorded in `LEARNINGS.md` only, so **L1 passing would be the
  signal** if the seam is ever fixed.

### Next
- **(1) Merge `phase-4-agent` → `main` and push** — **deferred, to be done deliberately later**; the
  whole phase has been **local-only** (local `main` is at the pushed Phase-3 state — `e1e2b72`, in sync
  with `origin/main`; all 4C work is on `phase-4-agent`, unmerged and unpushed).
- **(2) Deferred-and-optional future work, NOT 4C scope:** the §9.3 failure wrapper (tool failure →
  `insufficient_evidence`, incl. the openFDA 404 mapping); **4B report mode**; multi-agent
  orchestration. Each is its own gated step if/when picked up.
- **(3) The consolidated project report / resume rewrite** — the originally-deferred capture work, now
  that the build has authentic depth behind it.

---

## Phase 4C — live-tool slice RUN: regulatory_status (L2) + corpus control (Q2) pass live; trial_status (L1) a documented limitation (2026-06-13)

**AUTHORITATIVE STATUS:** **Phase 4C live-tool dispatch is built, committed, and DEMONSTRATED LIVE on
the clean entity-absence case; one route (trial_status / L1) is a documented limitation, not a bug.**
On branch `phase-4-agent`. The full 4C build chain is committed: the two API clients
(`clinicaltrials_lookup` `fbb3d66`, `fda_lookup` `7a8efe4`), the recorded fixtures (`1ed7221`), the
types/seam plumbing + `gap_kind` dispatch (`c55aaf2`, `3cc66f0`), the scorer record-identity
faithfulness + value-layer atoms (`a209ddd`, `50ae2c3`), and the live golden (`d40fdba`); the `httpx`
dependency gate (`3a6d740`) and the 4C contract docs (`73a0f8d`) preceded them.

- **What works LIVE (real Gemini, temp 0; fixture-backed tools — keyless, no network):**
  - **L2 — `regulatory_status` escalation, scored 1.0 END-TO-END.** "Is pitolisant approved?" → ASSESS
    `gap(regulatory_status, ['pitolisant'])` → `fda_lookup('pitolisant')` → openFDA record
    (`openfda:NDA211150`, record-identity span, `line_range=None`) → cited by SYNTHESIZE →
    terminal_state / recall / precision / faithfulness / expected_route all 1.0 / match.
  - **Q2 — corpus control holds.** Answers fazirsiran Phase III from the corpus, calls NO tool, scores
    1.0 — the corpus-first invariant proven (dispatch is discerning, not trigger-happy).
  - The 4C live-tool capability is **demonstrated on the clean entity-absence case.**
- **Known limitation — `trial_status` escalation for attribute-absence-with-present-subject (L1).**
  "Recruitment status of oveporexton's Phase 3 trial" → ASSESS returns `sufficient`/`corpus` and never
  escalates (it answers the corpus's regulatory "Filed" stage instead). This is the **4A I3
  attribute-vs-subject seam** (subject present, requested fact absent) and is **NOT prompt-fixable** —
  a narrow ATTRIBUTE CHECK was tried and produced a **byte-identical** verdict; **reverted, the
  committed prompt is unchanged.** Structural fix (ASSESS judging attribute-coverage, not
  subject-coverage) **deferred, out of 4C scope.** See `LEARNINGS.md` (2026-06-13).
- **Confirmed fact carried forward (for §9.3):** openFDA returns **HTTP 404 with an `{"error": ...}`
  body** on a zero-match search (NOT a 200 with empty `results`) — the §9.3 wrapper must map that
  no-match 404 to empty-evidence → `insufficient_evidence`, distinct from a real transport failure.
- **Golden unchanged:** `agent.golden.live.json` is left as authored — L1's entry expresses the
  intended (escalate → answered) behavior; the measured L1 failure lives in `LEARNINGS.md` only, so
  **L1 passing would be the signal** if the seam is ever fixed.

### Next
- **The committed MockTransport fixture-backed test suite (§6.5)** over the WORKING paths (L2
  `regulatory_status` + Q2 corpus; the dispatch / record-identity-faithfulness / value-atom chain),
  keyless and networkless.
- **Deferred (out of 4C scope): the §9.3 typed-failed-result wrapper** (tool failure →
  `insufficient_evidence`, incl. the confirmed openFDA 404-on-no-match mapping above). The clients
  **raise/propagate by design**; this is explicitly **NOT built in 4C** — a decided descope, not
  unfinished work (the no-match behavior is *characterized*, and the 404 fact stays recorded above if
  §9.3 is ever picked up later).
- L1 stays a documented limitation — do **not** keep tuning ASSESS against it.

---

## Phase 4C — DESIGN LOCKED: live-tools contract ratified; 4B deferred (2026-06-13)

**AUTHORITATIVE STATUS:** **Phase 4C (live tools) design is LOCKED; NO client code exists yet.** On
branch `phase-4-agent`. Docs-only: the 4C contract is recorded in `AGENT_PLAN.md` §9 (agent/tool
design) + `AGENT_CONTRACT.md` §6 (eval additions); `src/tools/` stays scaffold-only and
`agent.golden.json` is untouched.

- **Sub-phase ordering LOCKED: 4A → 4C; 4B deliberately deferred** (optional later piece). One-line
  rationale: 4B is **lowest-leverage / fuzziest-eval** (presentation over an already-cited answer),
  4C is **higher-value** (external-integration + the fixture-vs-live reproducibility story).
  Supersedes the old `AGENT_PLAN` §8 "4b gate before 4c" sequencing (reconciled in the same docs edit).
- **4C contract — LOCKED (full detail in `AGENT_PLAN` §9 + `AGENT_CONTRACT` §6; not duplicated here):**
  - **Go-live:** corpus-first, **absence-driven gap-fill**; **staleness/freshness explicitly RULED
    OUT** (no clean API as-of signal + corpus coverage). ASSESS emits a **closed-set gap-kind
    `{corpus, trial_status, regulatory_status}`**; **code owns kind→tool dispatch** (model names the
    gap, never calls the tool).
  - **Two tools:** `clinicaltrials_lookup` (CT.gov v2), `fda_lookup` (**openFDA only — NOT EMA**; the
    `src/tools/CLAUDE.md` EMA drift was corrected in the prior docs edit).
  - **Failure:** tool failure → **typed failed result → existing `insufficient_evidence`** (NO new
    terminal state); **trajectory-recorded** (failure-cause vs genuine absence); catch
    timeout/HTTP-error/malformed-body; **no retries** (relies on the §5.6 cap + §5.5 machine); **no
    cross-tool fallback**; openFDA key **env-read, absence non-fatal**; failure handling
    **unit-tested, not fixtured**.
  - **Live eval:** separate **`agent.golden.live.json` (`agent-golden-live-v1`)**, frozen golden
    untouched; **L1** (oveporexton recruitment → a Completed CT.gov trial) + **L2** (pitolisant/Wakix
    approval → openFDA) + **one reused corpus control**; **single-mode `live_enabled`**;
    **record-identity provenance** (`ctgov:<NCT>` / `openfda:<app_no>`, `line_range: null`,
    record-level containment); **`expected_route` tested-not-scored**; fixtures committed under
    **`src/evals/fixtures/`**, **transport-mocked**, **keyless eval**.

### Next — 4C build: dependency gate, then first tool client
- **4C contract locked, no client code yet.** Next build step is the **dependency gate (add `httpx`
  to `pyproject.toml`, with approval)** + the **first tool client** in `src/tools/` (mocked-HTTP unit
  tests, no live network), then the live golden + fixtures scored against the §6 contract.

---

## Phase 4A — COMPLETE: final measured result on step3; seam committed (2026-06-13)

**AUTHORITATIVE STATUS:** **Phase 4A is COMPLETE.** The research agent (PLAN/ASSESS/SYNTHESIZE Gemini
seam) runs end-to-end over the 13-question golden and is scored by the committed value-matching scorer.
`src/agent/gemini_seam.py` is now **committed** at its final, endorsed prompts (the granularity nudge in,
the failed citation-precision nudge reverted). On branch `phase-4-agent`.

- **Final measured result (step3, fully reproducible at temperature=0 — byte-identical claims across
  re-runs):** answered stratum (n=9) **terminal_ok 1.00, recall 0.56, precision 0.70, faithfulness
  0.77**; partially_answered (n=2) and insufficient_evidence (n=2) **terminal_ok 0.00** (the
  refusal-honesty architectural issue, below). Runs are gitignored scratch
  (`data/eval/reports/agent_step{1..4}.json`).
- **The measurement arc:** answered-stratum recall **0.00** (baseline) → **0.11** (SYNTHESIZE
  granularity nudge) → **0.56** (after the four committed scorer fixes that credit correct paraphrases
  without papering over agent errors). Each step was measured before the next; no end-to-end guessing.
- **Remaining gaps — cleanly decomposed (all characterized, none blocking):**
  - **Q3/Q4 — golden-phrasing / synonym** ("lifecycle register"; "China filing stage" vs "approval
    status in China"). Characterized; chasing them by tuning the agent would overfit to golden strings.
  - **Q5/Q6/P1 — genuine agent subject-granularity error** (company-level subject vs drug; drug
    unnamed). A real agent weakness, correctly left unmatched by the scorer.
  - **Q7/Q9 — citation precision** — a **retrieval/chunk-grain limitation on dense financial tables,
    NOT prompt-fixable** (the step4 citation-precision nudge was tried and REVERTED — it made chunk
    selection worse and bled into claim content; see `LEARNINGS.md`).
  - **Refusal honesty (P1/P3/I2/I3)** — `insufficient_evidence` is **architecturally unreachable via the
    ASSESS nudge alone** (the state machine routes `exhausted` + surviving claims → `partially_answered`).
    Needs the ASSESS-`exhausted` ↔ SYNTHESIZE-refusal coupling.

### Next — Phase 4A is DONE
- No further 4A tuning or runs. Future agent-side work, if any, is **subject-granularity** (Q5/Q6/P1) and
  the two architectural items (**finer-grained/line-level citation evidence** for Q7/Q9; the
  **refusal coupling** for the partially/insufficient strata) — all characterized, none blocking 4A.

---

## Phase 4A — 6b: full 13-question run (step1 baseline + step2 tuned); first eval numbers (2026-06-13)

**AUTHORITATIVE STATUS:** **Batch-6b step1 (pre-tuning baseline) AND step2 (one tuning iteration) are
both COMPLETE; the full 13-question agent has run end-to-end against real Gemini and produced the first
Phase-4A eval numbers.** On branch `phase-4-agent`. `src/agent/gemini_seam.py` is **still untracked /
uncommitted** (now carries the two step2 nudges). Saved run artifacts live in gitignored
`data/eval/reports/agent_step1.json` and `agent_step2.json`. **Nothing committed this step.** Quota:
step2 = **~39 Flash-Lite calls** (all 13 questions at 1 iteration; `2 + iterations` per question).

- **CORRECTION to the 6a entry below.** The 6a entry's "full run NOT yet done / quota ~3 calls" status
  is **stale** — the full baseline run (`step1`) DID happen (all 13 scored, saved to
  `agent_step1.json`). This entry supersedes it.
- **Two prompt nudges applied for step2** (both general, neither golden-memorizing): a SYNTHESIZE
  granularity nudge (carry indication/period/region/scope into the `attribute`) and an ASSESS
  subject-grounding honesty nudge. Scorer / golden / `AGENT_CONTRACT` / `retrieval.py` / `resolve.py`
  **untouched**.
- **First real eval numbers (step2, sliced per `AGENT_CONTRACT` §5).** Answered stratum (n=9):
  **terminal_ok 1.00, recall 0.11** (up from 0.00), precision **1.00 (/1)**, faithfulness **1.00 (/1)**.
  **Q1 is a perfect 1.0/1.0/1.0** — the first real-Gemini question scoring across all three claim
  metrics. partially_answered (n=2) and insufficient_evidence (n=2) strata: terminal_ok **0.00**
  (unchanged); insufficient_pass **0.00**. **The recall = 0.11 is measurement-limited — the agent's
  true answer quality is materially higher** (see `LEARNINGS.md` 2026-06-13 entry 1: causes A/B are
  scorer/value-parser limits, only C is genuine agent error).
- **TWO open issues, NEITHER resolved (and not to be papered over):**
  1. **Attribute matching** — real agent output exposed a **scorer-design limitation** (correct,
     value-matching paraphrases scored ~0.895 < the 0.90 difflib threshold; e.g. Q7 `"net sales for Q1
     2026"` vs golden `"Q1 2026 net sales"`). **The correct fix is an OPEN design question** — NOT
     necessarily Batch-2-style closed-set canonicalization, because attributes are compositional, not a
     finite closed set.
  2. **Refusal honesty** — `insufficient_evidence` is **architecturally unreachable via the ASSESS
     nudge alone** (the state machine routes `exhausted` + surviving claims → `partially_answered`);
     needs the ASSESS-`exhausted` ↔ SYNTHESIZE-refusal coupling. The agent's biggest genuine weakness.

### Next — focused design discussion on attribute matching (NOT a prompt tweak, NOT a threshold tweak)
- **First PARTITION the recall-zeros** into (i) scorer-should-have-matched, (ii) genuine-agent-error,
  (iii) golden-phrasing — then decide **whether/how** to change the scorer. **No threshold tweak without
  that partition.** Refusal honesty (issue 2) is a separate, architectural workstream.

---

## Phase 4A — 6a: LLM seams live on Q1; citation-faithfulness direction corrected (2026-06-13)

**AUTHORITATIVE STATUS:** **The three LLM seams (PLAN/ASSESS/SYNTHESIZE) make real Gemini calls and the
full pipeline is proven end-to-end on ONE question (Q1); a 6a-revealed scorer/contract correction is
committed. Full 13-question run NOT yet done (that is 6b).** On branch `phase-4-agent`. Quota spent so
far: ~3 Flash-Lite calls (the single Q1 run).

- **Real LLM seam (Batch 6a) — built, NOT yet committed.** `src/agent/gemini_seam.py` (`GeminiLLMSeam`)
  drives PLAN/ASSESS/SYNTHESIZE via `extraction.gemini_client.generate_structured` (same SDK / key /
  Flash-Lite / structured-output pattern; response-view models mirror `extraction.models`, no
  `extra="forbid"`). §5.7 honored: the model sees a 0-based NUMBERED evidence list (text only — no
  doc_ids / line ranges) and cites by INTEGER index. **Held back from commit** pending a 6b SYNTHESIZE
  prompt tweak.
- **Q1 run — all four plumbing checks PASS.** (a) structured output parses into the `types.py` schemas;
  (b) the model cites by integer index (schema-enforced `list[int]`), never doc_ids; (c) indices resolve
  to real spans via `resolve_citations`; (d) the Batch-2 scorer consumes the `ResolvedAnswerObject`.
  Two non-plumbing findings surfaced: (1) **citation grain** — fixed below; (2) **attribute phrasing /
  claim decomposition** — the agent said `"approval status"` vs golden `"approval status in IgA
  nephropathy"` (fuzzy 0.48 → unmatched → recall 0.0); **deferred to 6b prompt tuning**.
- **Citation-faithfulness direction CORRECTED (this commit).** The agent cites at **chunk grain**
  (`corpus_retrieve` returns chunk spans, e.g. `(432,486)`) while the golden blesses **sub-chunk** spans
  (e.g. `(443,445)`); the original `agent_span ⊆ acceptable_span` demanded a granularity the agent never
  sees. Reversed to **`acceptable_span ⊆ agent_span`** in `agent_metrics._span_contained` (binary,
  OR-semantics retained). `AGENT_CONTRACT.md` §3.4 updated with the corrected direction + the
  **boundedness assumption** (`corpus_retrieve` emits single-chunk-bounded citations, so an over-broad
  citation cannot arise from the real agent) + 6a provenance — a deliberate, documented change to a
  frozen artifact. A sixth sanity agent **`OVER_BROAD`** makes the flip's one false-positive (a
  document-spanning citation is faithful) explicit and out-of-scope-for-the-real-agent.
- **Trust gate re-verified (6 agents).** ORACLE 1.0 (reflexivity), CITATION_FAILURE still fails (its
  far-shifted span does not contain the golden span), HALLUCINATION/OVERCLAIM unchanged, OVER_BROAD
  faithful-and-documented. Suite **135**. (The Q1 chunk citation `(432,486) ⊇ (443,445)` is now faithful;
  shown on a matched variant — the captured Q1 claim itself stays unmatched on attribute pending 6b.)

### Next — Batch 6b: full 13-question run + first eval numbers
- Tune the SYNTHESIZE prompt toward the golden's claim granularity (the attribute-phrasing finding),
  run the full agent over all 13 golden questions, and score sliced (AGENT_CONTRACT §5) for the first
  full Phase-4A eval numbers. Commit `gemini_seam.py` with that pass.

---

## Phase 4A — agent loop + real corpus_retrieve + resolution wired; plumbing COMPLETE (2026-06-13)

**AUTHORITATIVE STATUS:** **Phase 4A agent plumbing is COMPLETE and tested WITHOUT quota; the
end-to-end contract is proven with stubbed reasoning. NO Gemini calls yet — the three LLM seams are
still stubbed.** On branch `phase-4-agent`, the research-agent control loop, the code-owned
terminal-state machine, the real `corpus_retrieve` tool, and the evidence-index→span resolution layer
are built and unit-tested (suite **135**). Committed:

- **Agent loop + state machine (Batch 4).** `src/agent/types.py` (PLAN/ASSESS/SYNTHESIZE output
  schemas, `EvidenceItem`, the `LLMSeam`/`RetrieverSeam` Protocols, the `Trajectory` record) +
  `src/agent/loop.py` (`run_agent`: PLAN once → [retrieve → ASSESS]* → SYNTHESIZE/refuse; hard
  max-iterations cap §5.6; the §5.5 terminal-state machine — terminal state assigned by CODE, never
  model-declared; §5.8 synthesis validation + one-retry degrade; loud-on-malformed verdict check). LLM
  + retriever are injected behind the seams (DI stubs in tests).
- **Real corpus_retrieve + resolution (Batch 5).** `src/agent/retrieval.py`: `corpus_retrieve(query)`
  = **chunk@10 ∪ fused@10**, span-deduped, **≤20 spans**, `k=10` fixed / non-agent-controllable (§5.3),
  **reusing the committed Phase 3 retriever** (`chunk_leg`, `entity_leg`, `rrf_fuse_by_span`) — no
  retrieval reimplemented; `CorpusRetriever` is the `RetrieverSeam` (fan-out per sub-query, union by
  span). `src/agent/resolve.py`: `resolve_citations` maps cited evidence indices → `(doc_id,
  line_range)` spans (§5.7). The loop now accumulates a **span-deduped numbered evidence table**.
- **Tested without quota.** `tests/agent/test_loop.py` (20) + `tests/agent/test_retrieval.py` (8):
  every §5.5 branch, the §5.6 cap, §5.8 degrade, the well-formedness raise, cross-iteration dedup, the
  union/dedup/chunk-text logic (mock + a **real-corpus smoke test** against the live FAISS indexes,
  134 chunk / 307 entity units), resolution, and the **end-to-end** stubbed-LLM loop → resolution →
  `ResolvedAnswerObject` → **Batch-2 scorer = 1.0** on golden Q1 (contract holds end-to-end).
  `fastembed` is local — no Gemini quota spent.

### Next — Batch 6: fill the three LLM seams with real Gemini calls
- Implement PLAN / ASSESS / SYNTHESIZE behind the `LLMSeam` (prompts + Gemini structured-output calls;
  model configurable, Flash-Lite per §5.1), then run the full agent over the 13-question golden and
  score with the validated Batch-2 scorer (sliced per AGENT_CONTRACT §5). **This is the first Phase-4A
  batch that spends quota.**

---

## Phase 4A — baseline evaluation harness COMPLETE + validated (2026-06-12)

**AUTHORITATIVE STATUS:** **Phase 4A (Q&A mode, corpus-only) baseline evaluation harness is COMPLETE
and VALIDATED; NO agent code exists yet.** On branch `phase-4-agent` (cut from `main`), the design is
locked in `docs/AGENT_PLAN.md` (incl. the §5.5 amendment `0e7760c`). The measurement was built and
proven **before** any agent (the Phase-2 measure-before-the-thing discipline). Committed:

- **Golden — FROZEN + committed** (`4b50c0c`). `src/evals/golden/agent.golden.json` (`agent-golden-v1`):
  **13 questions** (Q1–Q9, P1, P3, I2, I3 — gaps at I1/P2 intentional), **9 answered / 2
  partially_answered / 2 insufficient_evidence**, **21 reference claims**. Human-authored from source per
  AGENT_PLAN §4.1, then transcribed verbatim; full `document_id` doc_ids; Q2-c1 span L236–248.
- **Answer-object ↔ scorer contract — FROZEN + committed** (`117b258`). `docs/AGENT_CONTRACT.md`: the
  frozen interface the scorer + future agent build against so they **cannot drift** (cite-by-evidence-
  index answer-object, resolved-answer-object via `resolve_citations`, the four metrics, the §4
  insufficient rule, sliced within-stratum aggregation).
- **Answer-object schema — committed** (`4bdedb5`). `src/evals/answer_object.py` — Pydantic v2
  `AnswerObject`/`Claim` + resolved forms (`Span`, 1-based-inclusive `line_range`). The
  claims-empty-on-insufficient rule is a **scorer** criterion, not a schema validator (so the
  over-claim case stays representable).
- **Scorer — committed** (`1f10871`). `src/evals/agent_value_match.py` (deterministic value layer:
  closed-set canonicalizer for phase / status / count / indication_present + structured comparator for
  currency-magnitude & sign-preserved percentage-pair; **raises** on unrecognized shapes) +
  `src/evals/agent_metrics.py` (the four metrics: `terminal_state_correct`, `claim_recall` + wrong-value
  diagnostic, `claim_precision` [**matched-only**: unlisted claims excluded not penalized],
  `citation_faithfulness`; reuses `retrieval_scorer.line_containment`). Status atoms collapse
  filed+submission → one `pending_filing` atom; `approved` kept distinct.
- **Scorer trust gate — committed** (this commit). `tests/evals/test_agent_scorer_sanity.py`: five
  known-output sanity agents (null / oracle / citation-failure / hallucination /
  over-claiming-on-insufficient) × an **independently-derived, hardcoded** expected-score matrix
  asserted over all 13 questions (**65 cells**). **ORACLE scores 1.0 across every claim-bearing question
  including prose values** → the value layer round-trips the golden; citation-failure proves
  recall⟂faithfulness; hallucination proves matched-only precision both ways; over-claim proves §4 (not
  precision) catches insufficient-question confabulation. Suite **107 passing**.

### Next — agent implementation (NO agent code yet)
- Build the research agent against the frozen contract + validated scorer, in steps: **loop skeleton
  (code-owned PLAN–ASSESS–SYNTHESIZE state machine, unit-testable without API) → `corpus_retrieve`
  wiring (chunk@10 ∪ fused@10) → real Flash-Lite LLM calls**. `src/agent/` and `src/tools/` remain
  scaffold-only. The baseline answer/scorer harness now exists to measure that agent from day one.

---

## Phase 3 — MERGED to main (2026-06-12)

**AUTHORITATIVE STATUS:** **Phase 3 COMPLETE and merged to `main`; Phase 4 not started.** Branch
`phase-3-retrieval` was merged into `main` as a `--no-ff` **merge commit `22efdd2`** (full branch
history preserved, no squash — matching the Phase-2 PR-merge convention), and the
engineering-decisions writeup (`docs/ENGINEERING_DECISIONS.md`, commit `81d8499`) landed. A pre-merge
release-readiness audit ran clean — no secrets, no tracked data / indexes / reports, the `.gitignore`
`data/` mechanism is on `main`, 106 tests passing. This entry's commit also corrects three post-merge
stale doc references (`src/rag/CLAUDE.md` "no code exists yet"; `ARCHITECTURE.md` "design is a later
conversation") and documents the retrieval entry points (`retrieval_run`, `retrieval_gate_b`). **Not
yet pushed to `origin/main`** — local `main` is ahead, pending review. Phase 4 (research agent + live
tools) follows per `ARCHITECTURE.md` build order; not started.

---

## Phase 3 — COMPLETE (hybrid retrieval): span-keyed fusion adopted (Gate B-revised) (2026-06-11)

**AUTHORITATIVE STATUS:** **Phase 3 COMPLETE on branch `phase-3-retrieval`; ready for pre-merge
review.** Hybrid retrieval over the extracted corpus is built and measured — chunk-leg backbone +
lean entity leg + span-keyed fusion, scored by a span-based retrieval golden through a layered eval.
**NOT merged to main** — the merge is a separate reviewed step (like Phase 2 PR #1).

### Gate B-revised — fusion adopted
- **Fusion = `rag.fusion.rrf_fuse_by_span`** (cross-leg RRF keyed on the `(doc_id, line_range)` span
  identity; co-located chunk+entity units collapse, agreement sums). **Adopted** over naive
  disjoint-set RRF: lifts headline recall (@1 **0.518→0.681**, @3 **0.755→0.903**, @10
  **0.935→0.972**), eliminates single-fact dinging (single Δ@3 **−0.167→+0.056**), preserves the
  buried-asset lift (Q5 assets all top-10). Parameter-free (no weight/cutoff/N; `k_rrf=60` locked).
- **Impossibility finding (load-bearing):** parameter-free fusion **cannot preserve unique reach** —
  agreement-rewarding RRF structurally demotes unique-reach spans (Vanrafia **6→11→33**; span-keyed
  demotes harder). Recovery needs an uncalibrable slot-count → the **α/T lockout, third instance**.
  Logged as future work (parameter-bearing unique-reach fusion). See LEARNINGS 2026-06-11.
- **Architecture vindicated:** the displacement is a *fusion* property; the chunk-leg backbone serves
  Vanrafia standalone (rank 6) — why the chunk leg is the locked backbone and Stage A ships alone.
  **Fusion serves breadth; the backbone serves unique reach.**
- **Finer-chunk §A.6:** the aggregate/comparison gap is substantially entity-leg-addressable (Gate B)
  and span-keyed fusion captures most of that lift → residual gap small; finer-chunk re-chunking
  remains **deferred / logged, not actioned** (its main motivation is now served).

### Phase 3 — what was built + measured (the layered eval)
- **Retrieval (`src/rag/`):** chunk leg (`fastembed` bge-small + FAISS + BM25 + RRF over the 1500/200
  ingestion chunks, **134 units**); lean entity leg (`entity_leg.py` — serialized facts, **307
  units**, IDENTICAL mechanism so a null is trustworthy); **span-keyed cross-leg fusion**. Local,
  quota-free, config-isolated embeddings; indexes persisted to gitignored `data/rag/`.
- **Eval (`src/evals/`):** relevance policy v2 (two policy gates Q3/Q5 → §5 sibling rule + §3
  two-score comparison; full labeling pass; tripwire dry) → leg-agnostic **shared scorer** (A1,
  verified 10/10) → **Gate A** chunk baseline → **Gate B** entity decomposition → **Gate B-revised**
  fusion. Golden: `src/evals/golden/retrieval.golden.json`.
- **Key results:**
  - chunk leg **strong-on-localized / weak-on-distributed** (localized to coarse-chunk dilution of
    table-spread/buried signal; macro recall@k {0.518/0.741/0.741/0.903}, always reported sliced).
  - entity leg **confirmed non-null on aggregate/comparison** (the buried-extracted-fact reranking
    hypothesis, evidenced: Q5's IgAN assets chunk 18–49 → entity 1–5).
  - **two entity blindness modes measured:** Vanrafia (un-extraction — entity structurally 0);
    Q1 plasma (misclassification — **partially compensated by serialization, entity rank 3**).
  - **T structurally inert at chunk grain** (degenerate-bimodal containment; recall threshold-free).
  - **fusion agreement-vs-unique-reach tension** logged (above).
- **Open / future-work items:** parameter-bearing unique-reach-preserving fusion; finer-chunk §A.6
  re-chunking; the **comparison construct validated on Q5 only** (zero-qualifying-asset case still
  untested).

### Next — pre-merge review, then merge to main (separate step)
- Review branch `phase-3-retrieval`; merge → `main` as a reviewed PR (like Phase 2). Phase 4
  (research agent + live tools) follows per `ARCHITECTURE.md` build order.

---

## Phase 3 Stage A — Gate A REVIEWED + RATIFIED (2026-06-11)

**AUTHORITATIVE STATUS:** **Gate A reviewed + ratified (T inert; finer-chunk deferred post-Stage-B;
Stage A shippable); Stage B (entity leg) next.** A2b joined the verified retriever (A2a) to the
verified scorer (A1), the Gate-A artifact was produced and reviewed, and the decisions below are
recorded. Supersedes the A2a entry below as current state.

### Integration built
- `src/evals/retrieval_run.py` (`python -m src.evals.retrieval_run`) — wires `rag.chunk_leg` →
  `evals.retrieval_scorer` (**changed neither**; reused `line_containment` as the one overlap impl),
  scores all 9 scored golden queries (Q2 §7-excluded), and writes a pinned sliced report to
  **gitignored** `data/eval/reports/retrieval_gate_a.{json,md}` (regenerable; not committed). Suite
  **106 passing**.

### T-decision RATIFIED — structurally inert at chunk grain (deferred-with-trigger CLOSED)
- The golden-lock's deferred-with-trigger T decision (calibrate against the first real index)
  **resolves here as "inert."** Gate-A containment over the retrieved top-10 was **degenerate-bimodal**
  — of 37 golden spans, **29 ≈1.0, 8 ≈0.0, 0 fractional** — and macro recall@k was **identical at
  T=0.5 and T=0.99**. recall@k is therefore **threshold-independent for sub-chunk spans**: a finding,
  not a gap. **No T is pinned.** See LEARNINGS 2026-06-11 (Gate A).

### Gate-A chunk-leg BASELINE result (lead with the localization — the plasma discipline)
- **Localized:** strong on single/set-of-singles (**1.0 by @10**, mostly @1–3), weak on
  aggregate/comparison (**near-zero until @10**). The weakness **localizes to coarse-chunk dilution**
  of signal spread-across / buried-within mixed-content tables (Q4 CV pipeline; Q5's buried *extracted*
  IgAN assets). Macro recall@k {@1 **0.518**, @3 **0.741**, @5 **0.741**, @10 **0.903**} is **always
  reported sliced by type, never as the bare macro number**.
- **Backbone confirmed empirically:** the chunk leg **reached un-extracted Vanrafia at rank 6** (the
  approved IgAN asset the entity leg structurally cannot see) while **missing the three *extracted*
  IgAN assets** (mezagitamab r29, Fabhalta r18, zigakibart r49) buried in mashed tables. Reachability
  backbone validated; the **Stage-B hypothesis is identified** — the entity leg is hypothesized to
  help on *extracted-but-table-buried structured facts*.
- **Finer-chunk lever (§A.6) DEFERRED to post-Stage-B:** the aggregate/comparison gap partly overlaps
  Stage B's target (buried extracted facts), so re-chunking now would **confound** the entity-leg
  measurement. Re-evaluate after Stage B; a still-open lever, **NOT actioned**.
- **Stage A is shippable as a standalone Phase-3 result** (strong localized recall + explained
  localized weakness + resolved T + confirmed backbone), independent of whatever Stage B returns.

### Next — Stage B (entity leg)
- Build the entity index over extracted facts + the per-leg decomposition (chunk-only vs entity-only
  vs fused), measured against this Gate-A baseline in the extracted slice; **null contribution is the
  locked-acceptable outcome**. The scorer is leg-agnostic and ready. Do **NOT** touch chunk config /
  k_rrf / embedding / T (would confound A-vs-B).

---

## Phase 3 Stage A — A2a chunk-leg retriever BUILT + eyeball-verified (2026-06-11)

**AUTHORITATIVE STATUS:** **A2a (the chunk-leg retriever) is built and eyeball-verified; A2b (wire
into the scorer → sliced recall@k → Gate A) is next.** This is the project's **first retrieval
code**. Supersedes the A1 entry below as current state.

### Built (`src/rag/` — first retrieval code)
- `units.py` (leg-agnostic `RetrievalUnit(doc_id, line_range, text, kind, payload)`); `embeddings.py`
  (**SOLE** `fastembed` importer; `EMBED_MODEL` configurable, local default `BAAI/bge-small-en-v1.5`);
  `dense.py` (FAISS build/persist/load, cosine over L2-normalized, `id→unit` map + meta persisted);
  `sparse.py` (`rank-bm25` + signal-preserving tokenizer — drug codes/acronyms kept whole);
  `fusion.py` (RRF, `k_rrf=60`, no normalization/weight); `chunk_leg.py` (the retriever);
  `verify_a2a.py` (the eyeball harness); `tests/rag/test_chunk_leg.py`. Full suite **106 passing**.
- **Deps added (exactly 3, pre-approved by the locked design): `faiss-cpu`, `rank-bm25`, `fastembed`.**
- Index: **134 chunk units** (Takeda 34 + Novartis 100 — the **full corpus**; the backbone indexes
  everything, incl. un-extracted regions), persisted to **gitignored `data/rag/`** (never committed).

### Eyeball-verified (A2a gate — NOT scored)
- Machinery sane: `bge-small-en-v1.5` (dim 384), FAISS reloads, BM25 keeps `TAK-861`/`VAYHIA`/`Lp(a)`
  whole. **Q8** (known-item) golden chunk @rank 2 **YES**; **Q7** (trial) @rank 1 **YES** (the
  `ianalumab` exact token pulled it despite the haemolytic/hemolytic spelling gap — BM25 earning its
  place); **Q4** (aggregate) **NO** — the aggregate-dilution finding below.

### Pre-Gate-A finding (feeds the decision, NOT a fix-now)
- **Q4 aggregate dilution:** coarse 1500/200 chunks bury a sparse-TA's pipeline rows in a mixed-TA
  table, so the CV pipeline chunk didn't surface top-5. The concrete data point for the §A.6
  finer-chunk decision — **to be made on A2b's full sliced recall@k, not now**; machinery is sound,
  this is a retrieval-quality signal. See LEARNINGS 2026-06-11 (aggregate dilution).

### Next — A2b (Gate A)
- Wire the verified retriever into the verified scorer (`retrieval_scorer.py` is leg-agnostic and
  ready), produce the sliced **recall@{1,3,5,10}** curve + the containment distribution that
  resolves the **T decision** (§A.6). That is Gate A.

---

## Phase 3 Stage A — A1 shared scorer BUILT + VERIFIED (2026-06-11)

**AUTHORITATIVE STATUS:** **Stage A sub-step A1 (the shared retrieval scorer) is built and verified;
A2 (the chunk-leg retriever) is next.** No retriever, embeddings, FAISS, BM25, RRF, or index exist
yet. Supersedes the design-locked entry below as current state.

### Built
- **`src/evals/retrieval_scorer.py`** — the **leg-agnostic** shared scorer (the component both Stage A
  and Stage B plug into, so A-vs-B stays apples-to-apples). §2 containment (`line_containment`, the
  single line-interval overlap; **T a sweepable parameter**, never baked in), §5 clean-vs-
  `resolution_limited` split, §3 construct handlers (single / set-of-singles / comparison two-score /
  aggregate recall-fraction), §6 slicing, §7 exclusion. **Stdlib only — no new deps.** (Note:
  `grounding.py` had no line-*interval* overlap to reuse — `_cited_text` is token-presence; the
  interval overlap is defined once here.)
- **`tests/evals/test_retrieval_scorer.py`** — containment arithmetic, T-sweepability, clean/RL split,
  and the A1 gate (golden reproduction). Full suite **102 passing**.

### Verified (the A1 gate)
- The scorer reproduces the labeling-pass numbers **10/10** from the golden's own stand-in units:
  Q1 4/4, Q3 clean 3/3 + RL-slice 3, Q4 recall@1 0.875 / @2 1.00, Q5 presence 2/2 + attribute 3/4,
  Q6–Q10 1/1, Q2 excluded (§7). **T-invariant across T ∈ {0.01, 0.5, 0.99}** — containment is
  **bimodal (1.0/0.0)** over stand-in units, confirming the locked T-deferral finding (T cannot be
  calibrated until A2 produces real retrieved units; see LEARNINGS 2026-06-11 + `RETRIEVAL_PLAN.md`
  §A.6).

### Golden reconciliation (one logical fix, same commit)
- **Q5 slice convention reconciled to §6.** The golden's Q5 `sliced` prose was Novartis-scoped
  (`novartis_extracted 2/3`, `novartis_un_extracted 1/3`); reconciled to the **§6 corpus-wide
  partition** the scorer emits (`extracted 3/3`, `un_extracted 0/1`), with Vanrafia preserved as a
  descriptive note (Novartis's approved IgAN asset = the backbone signal). **Q5 scores untouched**
  (presence 2/2, attribute 3/4). **No schema-version bump:** the `sliced` field is descriptive/
  human-facing, the scorer derives its slice from member `slice` tags (not this field), and no loader
  validates the retrieval golden's structure. A scan confirmed Q5 was the **only** query with a
  scoped-denominator slice (the `rollup.by_slice` tally counts queries by slice tag, a different,
  consistent thing).

### Next — A2 (chunk-leg retriever)
- Build per `RETRIEVAL_PLAN.md` Stage A: `src/rag/{units,embeddings,dense,sparse,fusion,chunk_leg}.py`
  + `src/evals/retrieval_run.py`. Deps `faiss-cpu` / `rank-bm25` / `fastembed` added **then, with
  approval**; index to gitignored `data/rag/`. The scorer is ready to receive real ranked units; the
  T decision comes due at Gate A.

---

## Phase 3 — Retrieval DESIGN locked (Block 2 + Stage-A calls) (2026-06-11)

**AUTHORITATIVE STATUS:** **retrieval design locked; Stage A (chunk-leg) implementation NOT yet
started.** The staged implementation plan is approved and persisted as **`docs/RETRIEVAL_PLAN.md`**
(the design-locked reference Stage A builds against). No retrieval code, deps, or index exist — those
are built per stage, gated. Supersedes the golden-locked entry below as current state.

### Block 2 design locked
- **Retrieval unit:** chunk leg REQUIRED (baseline + reachability backbone, independently shippable);
  entity leg LEAN + layered, measured by per-leg span-decomposition in the extracted slice; **null
  entity contribution is acceptable**. Entity-only disqualified as primary (Vanrafia un-extraction +
  Q1 misclassification).
- **Embedding library: `fastembed`** (local, reproducible, quota-free, lightweight) — config-isolated
  (`gemini_client.py`/`_require_env` pattern), `EMBED_MODEL` configurable; index records model+version.
- **Score combination: RRF, `k_rrf=60`, no normalization, no tunable weight** (α uncalibrable here,
  same reason as T).
- **Target-k:** recall@k over k ∈ {1,3,5,10}, sliced by query type; operating-k deferred to Phase 4.
- **Module split:** retriever in `src/rag/`; **shared scorer in `src/evals/`** (reuses `normalize` +
  `grounding` overlap helpers) — built once, reused by both stages so A-vs-B is apples-to-apples.

### The two Stage-A calls
- **Reuse the existing 1500/200 ingestion chunk config** for Stage-A retrieval units (reuse
  `chunk_document`; don't write a second chunker). Retrieval chunking is an independent parameter but
  is **NOT changed now** — whether finer units are justified is a **Gate-A decision** on the
  containment + recall@k data.
- **T-calibration is the T-problem's third appearance** (`RETRIEVAL_PLAN.md` §A.6): coarse chunks keep
  containment **bimodal (1.0/0.0)** even with real retrieval, so T may prove **structurally inert at
  chunk grain** — if so, that is **reported as a finding**, not solved speculatively. Decided at
  Gate A. See LEARNINGS 2026-06-11.

### Staged structure (gated)
Stage A (chunk dense+BM25+RRF, scored vs golden, **T decided here**) → **Gate A** (sliced chunk-leg
recall@k + the T decision; reviewed before any entity work) → Stage B (entity index, per-leg
decomposition, **entity Δrecall incl. acceptable ≈0**) → **Gate B**. Each gate produces one
reviewable artifact (`RETRIEVAL_PLAN.md` has the full spec).

### Next — Stage A (chunk-leg) implementation (NOT started; needs its own kickoff)
- Build per `RETRIEVAL_PLAN.md`: `src/rag/{units,embeddings,dense,sparse,fusion,chunk_leg}.py` +
  `src/evals/{retrieval_scorer,retrieval_run}.py`. Deps to add **then, with approval**: `faiss-cpu`,
  `rank-bm25`, `fastembed`. Index persists to gitignored `data/rag/`.

---

## Phase 3 — Retrieval golden LOCKED + persisted (policy v2) (2026-06-11)

**AUTHORITATIVE STATUS:** Phase 3 is at **"retrieval golden locked + persisted; retrieval
design NOT yet started."** The retrieval relevance-criteria **policy v2 is LOCKED** and the
**retrieval golden v1 is persisted and tracked**. No retriever, embeddings, FAISS, BM25, fusion,
or any retrieval implementation exists or has been designed — that is the **next** conversation
(a retrieval **design** phase, which itself precedes any implementation planning). Do not read
this milestone as "retrieval started."

### What this milestone is
- A **labeling** deliverable, not a build one. The retrieval golden is the fixed input the
  (future) retrieval eval will score against — the Phase-3 analog of the Phase-2 extraction
  golden. It is authored from the **source documents**, never from extraction output.

### Persisted artifact
- **`src/evals/golden/retrieval.golden.json`** (TRACKED, like the extraction goldens; `data/`
  stays gitignored). New top-level schema `retrieval_golden_schema_version="1"` — it is
  **query-based + cross-document**, distinct from the per-document extraction goldens
  (`takeda`/`novartis.golden.json`, which carry `golden_schema_version`). Loadable structured
  data (not a flattened table); each query carries text / type / §3 construct / slice /
  `(doc_id, line_range)` golden spans + verbatim / per-span §1 + §5 verdicts / coverage
  structure. The full **policy v2** text + validation history are embedded in the file
  (`policy_v2`, `validation_history`) — that block is policy v2's canonical home.
- 10 seed queries: **9 scored, 1 (Q2 Avidity) §7-excluded** as unmodeled-entity (deal/M&A).
  Constructs: single ×5, set-of-singles ×1 (Q1), comparison ×1 (Q5), aggregate ×1 (Q4),
  single-per-region ×1 (Q3). Slice: extracted ×8, mixed ×1 (Q5), excluded ×1.

### Locked this milestone
- **Policy v2 locked** with two §3 clarifications added: (1) **bounded set-of-singles vs
  aggregate** is decided by *closed-and-query-defined* (the query names the facts; a literal
  source value like "Multiple Indications" does NOT make it an aggregate) vs
  *open-and-corpus-defined* (the corpus determines membership/count); (2) the **comparison
  construct** (two scores: presence + attribute coverage) is recorded as **validated on its
  motivating case only** (Q5) — a **known limitation**, NOT settled; the **zero-qualifying-asset
  case is untested** and it will be revised on the first future comparison that exposes a gap.
- **Validation history** (in-file): two gates (Q3 → §5 v2 sibling rule; Q5 → §3 v2 two-score
  comparison) + a labeling pass with a tripwire on the first new relational query. **Tripwire
  stayed DRY** — §3 v2 **aggregate** construct **validated** on Q4; pass ran to completion.
- **T (containment threshold) DEFERRED with a stated trigger** — not an oversight. Provenance
  `line_range`s as stand-in units bias containment to ≈1.0 (bimodal 1.0/0.0), so neither the
  gates nor the pass can falsify T. **Trigger: calibrate against the first real retrieval index**
  (where sub-T containment can occur). See LEARNINGS 2026-06-11.

### Findings carried forward (the backbone argument)
- **Two distinct entity-leg blindnesses**, both reachable only by the chunk leg: (a) **by
  un-extraction** — Novartis's only *approved* IgAN asset **Vanrafia/atrasentan** sits in an
  un-extracted chunk (`q1-2026…`, L443–445); (b) **by misclassification** — the Takeda plasma
  reg-events (L555–581 + progress) are in *extracted* chunks but emitted as Program `stage`, not
  `RegulatoryEvent`. These are the concrete, portfolio-valuable reasons chunk retrieval is the
  baseline/backbone (entity retrieval is a measured layer on top).
- Q3 is the canonical **resolution_limited** case (3 RL spans); Q5 the canonical **comparison**.

### Next — retrieval DESIGN conversation (NOT started; do not begin without kickoff)
- A fresh design phase (chunk-vs-entity retrieval units, embeddings model + quota, FAISS/BM25
  hybrid + fusion, retrieval metrics wiring) — **out of scope for this milestone by instruction.**
  Reminder from orientation: `faiss-cpu` + `rank-bm25` are NOT yet in `pyproject.toml` (deferred
  to phase start), and the embeddings model/quota is unpinned.
- The retrieval golden has **no loader module yet** (deliberate — a loader is retrieval-eval code,
  built when the retriever exists). The JSON is the contract.

---

## Phase 2 — COMPLETE: eval harness + golden baseline (2026-06-10)

**Current authoritative state** (supersedes the Stage 1 entry below). Branch
**`phase-2-evals`** (pushed). Phase 2 (evals + golden set) is **DONE**: the baseline
deliverable — a pinned, decomposed `report.md`/`report.json` via `python -m src.evals.run`
— is built, tested, and reviewed.

### Headline finding (the defensible baseline result)
- **Plasma-table reg-events are systematically missed.** Predicted reg-events in the
  IVIG/plasma chunks ch12/15/16 = **0/0/1**: Flash-Lite extracts the "Approved/Filed (date)"
  status cells as program *stages*, never as RegulatoryEvents — in the main table AND the
  progress rows. So reg-recall **0.41 localizes to the plasma pipeline**, not diffuse weakness.
- Aggregate (distinct facts): programs P **0.88** R 0.73 (+10 restatement census-artifact FPs),
  trials 1.00/0.83 (one real miss: APPLAUSE-IgAN prose trial), **reg P0.94 R0.41**, metrics
  1.00/1.00. Grounding: load-bearing tokens 97-100% PRECISE; region/stage DIRECTIONAL
  (chunk-granularity caveat); ~0.3% hard wrong-line rate.
- **Scope (stated, not hidden):** Takeda FULLY CENSUSED (8 chunks / full 34-chunk doc);
  Novartis reg census **slice-bounded** to the 12 extracted chunks (a full Novartis reg
  census needs the other 88 chunks extracted).
- **`judge.py` deferred** — an optional fuzzy-band (0.80-0.90) tie-breaker, not a baseline gate.

### Committed
- `2ff9c9f` **golden label schema + loader** (`src/evals/labels.py`) — key-agnostic
  per-document JSON; closed enums reuse the schema `Literal`s.
- `90010b9` **normalization + matching** (`src/evals/normalize.py`, `matching.py`):
  `canonical_term` + domain synonym maps, difflib `fuzzy_match` (≥0.90), `slug` (parity
  with `extractor._slug`), value-scale `to_base`/`values_match` (2% rel-tol); asset
  identifier-overlap union-find, per-type collapse keys, `collapse()`, and the
  predicted↔golden match predicates + `match_lists`.
- `365722e` Takeda **golden chunk 14** labeled + scored end-to-end; labeling policy adopted
  (`src/evals/CLAUDE.md`); `from_progress_row` on golden reg-events; agency rule (PMDA==MHLW).
- `5303825` Novartis **golden chunk 32** scored end-to-end; **company self-reference fix**
  (`normalize.fold_self_reference`: "Company"->source_company, excludes "Total") — chunk-32
  metric flips to 1 TP/0 FP/0 FN.
- `1c261f4` golden **batch** (Takeda chunk 12 IVIG cluster; Novartis chunks 29 standalone-reg
  + 30 RemIND-met/MARINA) + **labeling policies 1-3** (multi-region split; key-incomplete ≠ FP
  via `matching.is_key_incomplete`/`normalize.is_null_sentinel`; no manufactured region key).
- **This commit:** **`metrics.py`** (union scoping; per-type P/R/F1; reg-events at both grains;
  `key_incomplete` separate; document-level asset precision withheld; miss/FP/KI/attr-error
  lists carry `line_range`+snippet). `therapeutic_area` **reported descriptively, not scored**
  (open free-text → no taxonomy to grade against). 5-chunk **union** baseline: programs P=0.89
  R=0.69, trials 1.00/1.00, **reg P=1.00 R=0.27 (standalone 0.23 / progress 0.33 / region-
  collapsed 0.20)**, metrics 1.00/1.00; chunk-12 reg **0/7**; IVIG over-merge 3 distinct → 1.

### Locked this stage
- **Approved match keys:** Program `(asset, indication~, region, stage)`; Trial
  `nct_id→trial_name~→(assets+indication~+phase)`; RegulatoryEvent
  `(asset, action, indication~, region)` with **agency demoted** to a scored attribute;
  MarketMetric `(subject~, metric, geography~)` with **period demoted** to a scored
  attribute (defaults to `reporting_period`).
- **Scope-before-collapse rule** for `metrics.py`: scope raw predictions to the union of
  labeled chunk indices → collapse once → match the union of golden labels; never
  collapse-then-scope or sum per-chunk (double-counts). Asset P/R is document-level. See
  LEARNINGS 2026-06-10.
- **Asset clustering:** Option A (simple merge-on-any-shared-identifier) for v1; over-merge
  measured later (LEARNINGS 2026-06-10).

### Baseline deliverable — DONE
- `src/evals/run.py` (`python -m src.evals.run`) loads each artifact + golden, scores, grounds,
  and writes pinned `report.json` + `report.md` to gitignored `data/eval/reports/`. Pins
  extraction_model / prompt_version / judge_model(null) / git_sha / golden_schema_version.
  Emits the DECOMPOSED numbers (FP subcategories clean/KI/IV/restatement broken out; reg-events
  at both grains + plasma line; asset recall, precision withheld; grounding; scope statement).

### Next — Phase 3 (separate design conversation; NOT started)
- **Phase 3: FAISS + `rank-bm25` hybrid retrieval** over the extracted corpus, with retrieval
  evals (precision@k / recall@k) + groundedness, per `ARCHITECTURE.md` build order. A fresh
  design phase with its own handoff — do not begin without a Phase-3 kickoff.
- **`grounding.py` — DONE** (commit `1849a1d`; full-run over 307 facts reviewed). Provenance of
  load-bearing tokens is strong (asset 98% / action 100% / value 100% / indication 97%); region
  62% (11% inferred) + stage 53% (37% of failures are bare-number map-gap) are DIRECTIONAL with
  the chunk-granularity caveat; ~0.3% hard wrong-line rate. See LEARNINGS 2026-06-10. No
  row-level fix (deliberate).
- **Reg-event census — COMPLETE (12 chunks labeled).** Takeda [8,9,10,11,12,14,15,16] (full
  doc, fully censused) + Novartis [28,29,30,32] (slice-bounded — only 12 of 100 chunks
  extracted; Novartis full-doc reg census would need more extraction). Final aggregate:
  programs P0.78 R0.73, trials P1.00 R0.83, **reg P0.94 R0.41** (Takeda progress-row 9/19;
  Novartis standalone 7/20; region-collapsed 6/14 + 3/15), metrics 1.00/1.00.
  - **PLASMA THESIS CONFIRMED from both sides:** predicted reg-events in the IVIG/plasma
    chunks = ch12 **0**, ch15 **0**, ch16 1 — Flash-Lite extracts the plasma table's
    approval/filing status cells as program *stages*, never as RegulatoryEvents, in BOTH the
    main table and the progress rows.
  - **Trial FN resolved** (transient): the TAK-755 AIS trial matched once ch16 (where the
    model cited it) entered the union → Takeda trials 1/0.
  - Program precision (0.78) is partly a census artifact: progress-row chunks (14-16) restate
    main-table facts, and the model assigns inconsistent regions across chunks, so duplicate
    extractions don't collapse and register as FP. Reg-event headline unaffected.
- **Reg-event CENSUS** (stopping criterion as a census, not a sampled threshold): enumerate
  every reg-event-bearing chunk in BOTH docs (candidate list produced; prune Takeda 0,1 +
  Novartis 78,79,96–98 boilerplate). Takeda 7,8,9,10,11,15,16 are the SAME status-cell pattern as
  chunk 12 (scored 0/7), so censusing them will **push reg-recall below 0.27** — the finding
  strengthening (whole pipeline table, not one chunk), NOT a regression. Bulk-label later, each
  chunk satisfying metrics + grounding at once.
- Then runner.py + optional judge. Do NOT declare the Phase-2 baseline until the grounding
  sample + census are reviewed. Corpus has **zero NCT IDs** (nct_id key-tier untested).
- _(superseded sub-bullets retained below for the metrics design contract)_
- metrics.py (DONE this commit): scope raw → union of labeled chunks → collapse once →
  match union (never collapse-then-scope or sum per-chunk). Per-type P/R/F1; reg-events at BOTH
  grains (standalone vs progress-row, AND region-split vs region-collapsed); `key_incomplete`
  counted apart from clean FP. Asset recall over labeled chunks OK; asset **precision stays
  document-level** (gated on full asset set labeled — do NOT report off the 5-chunk batch).
  miss / FP / key_incomplete / attribute-error lists each carry source `line_range` + snippet.
- Then grounding + runner + optional judge. Do NOT declare the Phase-2 baseline until the
  inspectable lists are reviewed. Corpus has **zero NCT IDs** (nct_id key-tier untested).

---

## Phase 2 (Stage 1, COMPLETE) — Extraction persistence + both corpus artifacts (2026-06-09)

**Current authoritative state** (supersedes the Phase 1 entry below). Work continues on
branch **`phase-2-evals`**. Phase 2 is being built in two stages with a checkpoint
between; **Stage 1 is done** — both scoreable extraction artifacts are persisted —
*before* the eval harness (Stage 2).

### Work completed
- **Extraction persistence** — `src/extraction/persistence.py`: `save_extraction` /
  `load_extraction`, a versioned (`schema_version="1"`) self-describing JSON envelope
  (`meta` + `counts` + `result`) that round-trips an `ExtractionResult` losslessly.
- **Run CLI** — `src/extraction/run.py` (`python -m src.extraction.run --report takeda`):
  load → chunk → paced per-chunk extraction (4.5s) with progress logging → persist to
  `data/eval/extractions/` (gitignored via `data/`). Named presets for takeda/novartis;
  `--path/--company/...` overrides; `--limit` (first-N smoke test); **`--chunks 3,4,…`**
  (targeted slice → `<doc>.slice.extraction.json`, recording `selected_chunks` +
  `source_total_chunks` in `meta`).
- **`extract_document`** gained two backward-compatible kwargs: `delay_seconds=0.0`
  (proactive pacing, default off) and `on_chunk` (progress callback). Existing
  behavior/tests unchanged.
- Tests: **59 passing** (+4 persistence round-trip).

### Baseline artifacts (the input Stage 2 scores against)
- `data/eval/extractions/qr2025_q4_Pipeline_table_en.extraction.json` — Takeda, full
  document, 34/34 chunks. Counts: **a150 / p178 / t5 / r13 / m0**.
- `data/eval/extractions/q1-2026-interim-financial-report-en.slice.extraction.json` —
  Novartis, **12-chunk slice** `[3,4,12,13,15,16,18,28,29,30,31,32]` (trial-/metric-heavy
  only; selected by chunk-level signal density). Counts: **a74 / p54 / t6 / r11 / m40**.
- Both zero-failure, model `gemini-3.1-flash-lite-preview`, git_sha `bace5ce` / `9129cec`.
- **Combined corpus:** assets 224, programs 232, **trials 11**, regulatory_events 24,
  **market_metrics 40** (assets duplicated per-chunk by design). The Novartis slice is
  what makes trial-recall + market-metric scoring measurable (Takeda alone: t5, m0).

### Decisions / notes
- Extraction output is now a **persisted, versioned artifact** under gitignored `data/`,
  never held in memory / `/tmp` (see LEARNINGS 2026-06-09).
- Snippet fallback to chunk text is visible on mashed table rows; duplicate facts are
  present by design. Both are **Phase-2 eval measurement targets, not Stage-1 bugs**.
- **Two matching-design issues the real artifacts surfaced** (to resolve PLAN-FIRST
  before harness code, since they touch the approved keys): (1) `MarketMetric.period`
  came back `'not specified'` (stated once globally, like `as_of_date`) — decide whether
  `period` stays a hard match key (defaulted from doc context) or becomes a scored
  attribute; (2) `MarketMetric.value` unit-scale varies (`1.3 billion` vs `184 million`)
  — value comparison must normalize scale.

### Recommended next step
- **Stage 2 — eval harness.** PLAN-FIRST on the two matching-design issues above, then
  build the module layout (golden label schema + loader → normalize → matching →
  grounding → metrics → optional judge → runner). Build the **golden label schema +
  loader FIRST** and checkpoint the label-file format against the real artifacts before
  any hand-labeling.

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
