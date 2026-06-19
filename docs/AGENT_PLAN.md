# AGENT_PLAN.md — Phase 4 research agent, locked design (DESIGN-LOCKED)

> **Status (2026-06: superseded).** This was the design-time plan for the Phase 4 research agent, written before implementation and locked prior to any code. Phase 4 (4A corpus Q&A and 4C live tools) is built and committed; this document is retained as a record of the design as planned, not as current status. For the system as actually built and the current working state, see HANDOFF.md. This document plays the
> role for Phase 4 that `docs/RETRIEVAL_PLAN.md` played for Phase 3 — it is the locked plan the
> build is **gated against**. It owns the *agent* design; system design lives in
> `ARCHITECTURE.md`, run/debug rules in `CLAUDE.md` (root) + `src/agent/CLAUDE.md` +
> `src/tools/CLAUDE.md`, the decision-making principles in `ARCHITECTURE.md` →`ENGINEERING_DECISIONS.md`.
> No agent code, schemas, or scaffolding exist yet — those are built per stage, gated. **Prompt
> text for PLAN / ASSESS / SYNTHESIZE is implementation, not design, and is explicitly out of
> scope for this document.**
>
> Built on the Phase 1–3 stack (extraction → eval harness → hybrid retrieval, merged to `main`
> at `22efdd2`). Where this plan cites Phase 3 numbers they are the repo's exact figures from
> `docs/HANDOFF.md` and `docs/LEARNINGS.md` (2026-06-11).

---

## 1. Purpose & Scope

Phase 4 is a **single research agent** sitting over the Phase 1–3 stack. It plans a retrieval
strategy for a competitive-intelligence question, gathers evidence through the locked Phase 3
retrieval, and synthesizes a **grounded, cited** answer — measured by an offline eval harness, the
same discipline that governed every prior phase.

It is built in **three gated stages**, each ratified before the next opens:

- **4a — Q&A mode, corpus-only.** A single question in, one cited answer out, over the static
  extracted corpus. **This is the primary subject of this plan.**
- **4c — live tools (the next stage after 4a — see the ordering lock below).** Adds
  `clinicaltrials_lookup` and `fda_lookup` (external API clients in `src/tools/`), evaluated against
  **fixtures** with a **live demo**. Contract **LOCKED in §9** (and the eval-side additions in
  `AGENT_CONTRACT.md` §6).
- **4b — report mode (DEFERRED, optional).** The *same agent*, driven at a composition level (a
  multi-question brief rather than one question). **Deliberately deferred and reordered after 4c**
  (ordering lock below); it remains an optional later piece, never a blocker. The report **contract
  is deferred to its own gate** — 4b is named here so the 4a design does not accidentally preclude
  it, not specified here.

**4c is the designated cut point.** The project is shippable and tells a complete story at the end
of **any** stage: 4a alone is a defensible corpus-grounded CI agent; 4c adds currency; 4b (if built)
adds composition. We build toward 4c but the project **ends whole at any gate** — no stage leaves a
half-finished artifact behind.

### Sub-phase ordering — LOCKED: 4a → 4c (4b deferred)

The build order is **4a → 4c**, with **4b deliberately deferred** to an optional later piece. The
rationale: **4b is the lowest-leverage stage** — it is presentation / composition layered over an
already-cited answer, and its eval is the **fuzziest** (a multi-question brief has no crisp
claim-level golden the way 4a and 4c do). **4c is the higher-value stage** — it adds a genuinely new
capability (**external API integration**, the live clinical/regulatory layer) and a stronger
**reproducibility story** (the fixture-vs-live eval). Sequencing the higher-value, more-measurable
stage first maximizes what the project demonstrates at its cut point. **This supersedes the earlier
"4b gate before 4c" sequencing recorded in §8** — 4b, if it is ever built, follows 4c.

### Motivation is evidenced, not aspirational

The agent exists because the Phase 3 evidence says a single retrieval call is structurally
insufficient for the questions that matter, and because the corpus has known blind spots a live
layer (4c) is designed to cover:

1. **Relational questions need planning.** Gate A measured the chunk leg **strong on localized
   facts** (single / set-of-singles reach 1.0 by @10, mostly @1–3) but **comparison and aggregate
   queries near-zero until @10** — a weakness that localizes to coarse-chunk dilution of signal
   spread across or buried within mixed-content tables (`docs/LEARNINGS.md`, Gate A). A single
   `corpus_retrieve` call cannot assemble a scattered, multi-part answer; **decomposing the
   question into sub-queries is the structural response.** This is the agent's reason to exist in
   4a.
2. **Corpus facts decay, and some facts are simply not extracted.** Every extracted fact carries an
   `as_of_date`; static corpus facts go stale. Separately, the **un-extraction blindness mode** is
   real and measured — Novartis's only approved IgAN asset **Vanrafia (atrasentan)** lives in an
   un-extracted chunk, reachable by the chunk backbone but absent from the entity index
   (`docs/LEARNINGS.md`, two entity-leg blindnesses). Both staleness and un-extraction are **4c's
   targets — named here, solved there** (a live lookup answers what the static corpus cannot).

### Explicitly NOT in Phase 4

These are out of scope and stay out — each is a deliberate cut, not an oversight:

- **Multi-agent orchestration** — a standing non-goal (`ARCHITECTURE.md` → Non-goals), deferred.
- **Monitoring / watchlist** (standing-query change detection) — an extension-list item, not built.
- **Extraction-QA agent** (an agent that audits/repairs extraction) — an extension-list item, not
  built.

---

## 2. Agent Contract (D1)

The contract fixes **what the agent promises** before any mechanism is designed — what it will
answer, what it refuses, the states it can end in, and the shape of what it returns.

### 2.1 In-scope question types

All **four constructs** from the locked retrieval relevance policy: **single**, **set-of-singles**,
**comparison**, **aggregate**. Singles are in-scope **deliberately** — they are the cases that test
**when *not* to plan**: a well-behaved agent must recognize a single-fact question and *not* fan it
out into a multi-sub-query search. Keeping singles in the contract makes "did the agent over-plan?"
a measurable property rather than an untested assumption.

### 2.2 Out of scope

- **§7 unmodeled-entity content** — deals / M&A (the Avidity-style acquisition content the retrieval
  golden excludes as Q2). The schema does not model it; the agent does not answer it.
- **Live-data questions** — anything requiring current clinical/regulatory state beyond the static
  corpus is **4c**, not 4a.
- **Report composition** — multi-question briefs are **4b**, not 4a.

Out-of-scope questions resolve to **`insufficient evidence` with receipts** — the agent states what
it looked for and did not find — **never undefined behavior**. Refusal is a defined terminal state,
not a crash or a guess.

### 2.3 Terminal states

Exactly three: **`answered`** / **`partially answered`** / **`insufficient evidence`**. The terminal
state is **code-assigned from the trajectory**, **never model-declared** — the model judges evidence
sufficiency (see ASSESS, §5.4), but the state machine (§5.5) sets the label. A model that says
"answered" does not make it so.

### 2.4 Answer-object

The structured thing the agent returns:

- the **terminal state**;
- **atomic claims**, each carrying: prose **text**, a **three-slot key** (subject / attribute /
  value — §3), and **citations resolved to `(doc_id, line_range)`** spans;
- an **evidence summary** on non-`answered` states (what was searched, what gaps remain — the
  receipts that make a refusal inspectable);
- **no confidence scores.** This is a **refused knob** — there is no calibration methodology on this
  corpus/golden to set a confidence number honestly, so emitting one would be a system that *looks*
  calibrated while guessing (the `ENGINEERING_DECISIONS.md` rule). Discrimination the agent cannot
  justify numerically is left to citation faithfulness instead.

### 2.5 Trajectory record

The trajectory is a **first-class artifact**, not debug exhaust: **machine-readable, schema'd, and
persisted per run** to a **gitignored** location (the same `data/` discipline as the Phase 2/3 eval
reports), referenced by a **run ID**. The distinction is load-bearing:

- the **answer-object** is *what the agent asserts*;
- the **trajectory** is *what the agent did* (the PLAN output, each ASSESS verdict, every
  `corpus_retrieve` call and its returned spans, repair events, the state transitions).

**The trajectory is a primary input to evaluation** (§4.4), not an afterthought — Phase 4 scores
behavior, not just the final answer, so the record of behavior is a deliverable.

---

## 3. Claim Key Specification

Every atomic claim carries a **three-slot key: subject / attribute / value.** (E.g. *subject* =
asset/company, *attribute* = the property asked about, *value* = the answer.)

**Three slots is the ceiling, by design.** A fourth slot would be **rebuilding the Phase 1 schema
inside the answer-object** — re-deriving region/stage/phase discriminators the extraction layer
already owns. Finer discrimination than three slots afford is resolved through **citation
faithfulness** (does the cited span actually support the claim, §4.3) — **not** by growing the key.

**All three slots are open strings**, compared via the **existing `src/evals/normalize.py`
machinery** at compare-time (canonical-term / domain synonym maps, value-scale `to_base` /
`values_match`). **The claim object never carries enums** — this is the standing open-vocab schema
rule that has held since Phase 1 (out-of-vocab values pass through verbatim; coercion to an enum is
how multi-TA breadth gets silently dropped). *Expect the build agent to want to tighten these slots
into enums "for safety"; that is the exact move the schema lock forbids.*

**Lineage:** Phase 2 scored **facts**, Phase 3 scored **spans**, Phase 4 scores **claims**. Each
phase's unit of evaluation is one level up from the last.

---

## 4. Evaluation Plan (D2)

The measurement is built **before** the thing it measures — the project's first principle. The
golden exists before the agent (§4.1, §8), so "is the agent good?" is a number from the first run,
not a retrofit.

### 4.1 Golden artifact

A hand-authored set, one entry **per question**, each carrying: the question **text**, its
**construct**, the **expected terminal state**, and a **reference claim set** (the keyed claims that
constitute a correct answer **plus the acceptable source spans** for each).

**Authored from source, before the agent exists — never from agent output.** This is the
**contamination rule**, stated here as a **gate condition**: golden authoring is the *first* build
activity of Phase 4 (§8), and no line of agent code is written until it is done. Labeling from agent
output would make the eval grade the agent against itself — the same authored-from-source discipline
that governed the Phase 2 extraction golden and the Phase 3 retrieval golden.

### 4.2 Size

**12–16 questions**, composed so that **every construct and every terminal state is non-trivially
represented** (including `insufficient evidence` — a refusal the agent should reach, e.g. an
out-of-scope or genuinely-unanswerable question). **Scale-calibration caveat:** a set this size can
**rank-order design decisions** (is approach A better than B?) but **cannot resolve fine parameter
tuning** — the identical honesty the 9-query retrieval golden was held to. Numbers off this golden
choose between structures, not between hyperparameters.

### 4.3 Answer-level metrics

- **Terminal-state correctness** — did the agent reach the expected state?
- **Claim recall** — did it produce the reference claims?
- **Claim precision** — **the hallucination metric**: did it assert claims that aren't supported?
- **Citation faithfulness** — does each claim's cited span actually contain the claim, by **span
  containment**. This is the **one legitimate reuse of a Phase 3 mechanism**:
  `src/evals/retrieval_scorer.line_containment` (the single line-interval overlap implementation),
  applied here to the agent's resolved citations.

### 4.4 Trajectory-level metrics

Scored off the §2.5 record, because Phase 4 evaluates behavior:

- **Planning efficiency on singles** — `len(sub_queries)` from PLAN on single-construct questions.
  A single should produce a **degenerate one-element** sub-query list; fan-out here is over-planning
  (the §2.1 "when not to plan" test made measurable).
- **Stopping behavior** — iterations to termination, **especially on `insufficient evidence`
  questions**: does the agent stop when the evidence is exhausted, or churn against the budget cap?

### 4.5 Reporting

**Sliced by construct × terminal state, never reported bare.** A single aggregate number hides
exactly the localization that every prior phase's findings depended on (Gate A's macro recall hid
the comparison/aggregate weakness until sliced). The slice is the finding.

### 4.6 Matching

- **Deterministic** on normalized **(subject, attribute)**; **normalized-compare** on **value** (the
  `normalize.py` value-scale machinery).
- **Fuzzy-text fallback** where the deterministic key does not bridge.
- **LLM-judge deferred** — an **optional tie-breaker, not a gate** (the unchanged Phase 2 posture:
  `judge.py` was specced as an optional fuzzy-band tie-breaker, never a baseline gate). It is not a
  dependency of the 4a result.

### 4.7 Logged limitations (eval)

- **Key/text prose divergence is unscored** — when a claim's three-slot key matches but its prose
  text says something subtly different, the harness does not catch it. A known gap, named not hidden.
- **The Phase 3 recall@k curve was measured on the raw golden queries, not on the agent's decomposed
  sub-query distribution.** Decomposition likely makes each individual `corpus_retrieve` call
  *easier* (a sub-query is more localized than the parent question), so the Gate A curve **likely
  understates per-call recall** in the agent's actual usage — but this is **unmeasured**, stated as a
  caveat on reusing the Gate A numbers, not a claim.

---

## 5. Architecture (D3)

The mechanism — chosen to make the §4 evaluation possible, and to respect the binding resource.

### 5.1 Model

**Flash-Lite, locked** (`gemini-3.1-flash-lite-preview`) — the same **constraint-first identity** as
extraction: the model was chosen because free-tier **requests-per-day** is the binding limit, not on
a quality claim. **Revisit only on a concrete capability failure found in eval**, never speculatively.

**Limits designed against:** **15 RPM / 250k TPM / 500 RPD.** The **binding resource is RPD** —
every LLM call (PLAN, ASSESS, SYNTHESIZE) spends one of 500 daily requests. **Tokens are the slack
resource** (per-call payloads are small relative to 250k TPM). **Resource-asymmetry note:**
`corpus_retrieve` uses **local `fastembed` embeddings and BM25 — zero Gemini requests** — so
retrieval is effectively free against the binding limit, and the agent's cost is **entirely its LLM
call count.** This asymmetry drives the whole loop design: minimize calls, not retrievals.

### 5.2 Loop ownership

**Code-owned control flow.** Native function-calling (letting the model decide when to call tools
and when to stop) was **considered and declined**, for reasons specific to this project — this is the
**interview-preempt** decision (the one a reviewer will ask "why not just use function-calling?"):

- **Trajectory-first eval (§4.4) demands code-owned sequencing** — to score planning efficiency and
  stopping behavior, the harness must *own* the step structure, not reconstruct it from opaque model
  tool-call traces.
- **Terminal-state discipline as code branches** — the three terminal states (§2.3) are code
  decisions over the trajectory, not model declarations; a code-owned loop is where that branch
  lives.
- **Extraction-pattern lineage** — the project already runs the LLM as a structured-output callee
  inside a code-owned loop (per-chunk extraction), not as an autonomous driver. Phase 4 keeps that
  shape.
- **Replay / debuggability** — a code-owned loop with a schema'd trajectory replays deterministically
  and is unit-testable without the API (§5.5).

### 5.3 `corpus_retrieve` contract

Signature shape: **`(query: str) → ≤20 spans`**, where the returned set is

> **chunk@10 ∪ fused@10**, deduplicated on the **span key `(doc_id, line_range)`**, each surviving
> span carrying its **chunk text + `(doc_id, line_range)`**.

- **k = 10 is set from Gate A evidence**, not chosen: chunk-leg macro recall@k reaches **0.903 at
  @10**, and **comparison / aggregate answers are only reachable at @10** (near-zero until then). Ten
  is the depth where the relational constructs become answerable at all.
- **The union operationalizes the fusion-impossibility finding.** Span-keyed fusion serves
  **breadth** (it lifts headline recall), but **parameter-free fusion structurally cannot preserve
  unique reach** — the un-extracted **Vanrafia** sits at **chunk rank 6**, **naive-fused rank 11**,
  **span-keyed-fused rank 33**: the more-correct fusion demotes the unique-reach span *harder*
  (`docs/LEARNINGS.md`, span-keyed fusion). So `fused@10` alone would lose Vanrafia, while
  `chunk@10` retains it. **Fusion serves breadth; the chunk backbone serves unique reach** — the
  union takes both legs' top-10 precisely so neither failure mode is in the agent's blind spot.
- **"≤20" is arithmetic, not a tuned parameter** — it is `10 + 10` before span-key dedup (fewer when
  the legs agree). **Recorded verbatim:** there is no "20" knob; it falls out of `k = 10` on two
  legs.
- **Depth is fixed, not agent-controllable** — **refused knob #5** (§6). The agent cannot widen or
  narrow retrieval depth; `k` is evidence-set and the same for every call, so retrieval reach is a
  measured constant, not a per-call guess.

### 5.4 Step taxonomy — exactly three LLM call types

Every Gemini request the agent makes is one of three kinds, and no others:

- **PLAN (1 call per question)** — question → a **sub-query list**. A single-construct question
  yields a **degenerate one-element list** (not a separate code path — the same PLAN step, which is
  why "did it over-plan?" is measurable, §4.4). Planning is the structural answer to the relational
  weakness (§1).
- **ASSESS (1 call per iteration)** — the evidence gathered so far → a verdict: **`sufficient`** /
  **`gap`** (with the **named missing slots** and **follow-up sub-queries**) / **`exhausted`** (with
  the **named gaps** that remain). ASSESS **judges only — it never writes the answer.** Separating
  the judge from the writer is what keeps terminal-state assignment honest.
- **SYNTHESIZE (1 call per question)** — the final evidence → **claims**. It runs **only** on
  `sufficient`, or on `exhausted`-with-partial-evidence (never on nothing — §5.8).

**Cost form: `2 + iterations` LLM calls per question** (PLAN + SYNTHESIZE = 2, plus one ASSESS per
iteration), **+1 in the worst case for a SYNTHESIZE repair** (§5.8). **Eval-run budget math:**
per-question worst case is `iterations + 3` requests; for the full 12–16-question suite that is
`(iterations + 3) × N`, and `corpus_retrieve` adds **zero** requests. Even at a generous handful of
iterations per question the whole suite costs on the order of low-hundreds of requests — a fraction
of the **500 RPD** budget, leaving room to run the eval several times a day. RPM/TPM stay slack with
the Phase-1 inter-call pacing carried forward. (The exact iteration cap is deferred — §5.6 — so this
math is parametric in `iterations`, not pinned to a number.)

### 5.5 State machine (code)

The loop, owned in code. **Every branch conditions only on code-held values — the ASSESS verdict,
the validation outcome (§5.8), and the surviving-claim count — never on model self-assessment.** The
terminal state is computed from these, not declared by the model:

- ASSESS **`sufficient`** + SYNTHESIZE output **survives validation with no claims dropped** →
  **`answered`**.
- ASSESS **`sufficient`** + the validation **degrade path dropped one or more claims** (§5.8) →
  **`partially answered`**.
- ASSESS **`exhausted`** + **one or more surviving claims** → **`partially answered`** (always —
  `exhausted` means named gaps remain, so `answered` is **unreachable** from this branch).
- **No surviving claims on any path, or the budget cap is hit** → **`insufficient evidence`**, with
  **trajectory receipts** (what was searched, what gaps remain).

The state machine is **unit-testable without any API calls** — feed it canned ASSESS verdicts and
assert the transitions and the terminal state. This testability is one of the reasons the loop is
code-owned (§5.2).

### 5.6 Budget

A **hard max-iterations cap, enforced in code from day one** — the loop can never run unbounded,
even before the cap's value is known. **The cap *value* is deferred**, to be **set from observed eval
behavior** (how many iterations real questions actually take before ASSESS converges). This is a
**deferred parameter, not a missing one**: the mechanism (a hard cap + the `insufficient evidence`
branch it triggers) exists from the first commit; only its number waits for evidence — the same
deferred-with-a-trigger discipline as the Phase 3 T-calibration.

### 5.7 SYNTHESIZE provenance

The model **cites by evidence index only.** SYNTHESIZE is shown a **numbered, de-duplicated evidence
list**; it references evidence by **index number**, and **doc IDs / line ranges are never shown to
the model as citable material.** **Code resolves index → span** via the lookup table after the call.

This carries the **Phase 1 grounding rule** forward: the model **structurally cannot invent
provenance** — it never sees a `(doc_id, line_range)` to fabricate, only an index into evidence the
code actually retrieved. The effect is that **fabrication is degraded from an uncatchable lie into a
scored citation error**: the worst the model can do is cite the wrong *index*, which §4.3 citation
faithfulness catches deterministically.

### 5.8 Validation & repair

SYNTHESIZE output is validated and, if needed, repaired deterministically:

- **Pydantic parse** of the claims;
- **index-range + non-empty checks** (every cited index exists in the evidence table; claim fields
  populated);
- on failure, **one retry with the named errors**, then **deterministic degrade** — **keep the valid
  claims, drop the invalid ones, record the drops in the trajectory, and let the state machine
  reflect the survivors** (a partial synthesis becomes `partially answered`, not a crash).
- **An empty claim list is *valid output*, not an error → `insufficient evidence`.** Synthesis must
  **never be coerced into asserting** something the evidence does not support; "I found nothing to
  claim" is a legitimate, honest result, routed to the refusal state.

---

## 6. Refused Knobs & Deferred Parameters

The consolidated discipline — **this section is the pitch.** It extends the project's established
refuse-uncalibrable-knob lineage (Phase 2–3: weighted-fusion **α**, containment **T**, the
unique-reach **slot count** — three instances of one rule, `docs/LEARNINGS.md`) into Phase 4.

### Refused — these knobs do **not** exist

| Refused knob | One-line reason |
|---|---|
| **Confidence scores** | No calibration methodology on this corpus/golden — a number that looks calibrated while guessing (§2.4). |
| **Agent-controlled retrieval depth** (knob #5) | `k = 10` is set from Gate A evidence; per-call depth control reintroduces an uncalibrable knob (§5.3). |
| **REFLECT / critique step** | A fourth LLM call type with no evidence it improves answers, spending the binding resource (RPD); ASSESS already judges sufficiency. |
| **REPLAN step** | Redundant — ASSESS's `gap` verdict already emits follow-up sub-queries inside the loop; a separate replan call costs RPD for nothing. |
| **Per-sub-query relevance filtering** | An uncalibrable filter over an already-small `≤20`-span set, costing RPD; ASSESS/SYNTHESIZE see the evidence directly. |
| **Tool-choice step** | Vacuous in 4a — there is exactly one tool (`corpus_retrieve`); tool selection returns only when 4c adds more tools. |
| **Multi-agent orchestration** | Standing non-goal (`ARCHITECTURE.md`), deferred. |

### Deferred to evidence — mechanism exists, value waits

| Deferred parameter | When it resolves |
|---|---|
| **Max-iterations cap** | Hard cap enforced from day one; its *value* set from observed eval behavior (§5.6). |
| **LLM-judge tier** | Optional tie-breaker, calibrated only if eval shows a fuzzy-band ambiguity worth breaking (§4.6). |
| **4b / 4c contracts** | Specified at their own gates (§1, §8), not pre-committed here. |

---

## 7. Logged Limitations

Consolidated, named-not-hidden — carried from §4.7 plus the context-growth note:

- **Key/text prose divergence is unscored** (§4.7) — a claim whose three-slot key matches but whose
  prose subtly diverges is not caught.
- **Recall@k measured on raw golden queries, not the decomposed sub-query distribution** (§4.7) —
  decomposition likely makes each `corpus_retrieve` call easier, so the Gate A curve **likely
  understates** the agent's per-call recall; **unmeasured**.
- **ASSESS context growth is bounded only at this corpus scale.** With ~3 iterations × ≤20 spans, the
  evidence ASSESS reviews stays small enough to pass whole into one call. **This would not hold at,
  say, 50 documents** — at larger corpus scale the accumulated evidence would outgrow a single
  ASSESS context and force an evidence-summarization or windowing mechanism this design does not
  have. A scale limitation, stated, not solved (no speculative mechanism for a scale we do not run at).

---

## 8. Stage Gates

Phase 4 follows the project's standing gated cadence — one reviewable step per turn, ratified in
chat before the next opens.

- **Golden authoring is the FIRST build activity of Phase 4 — before any agent code — per the §4.1
  contamination rule.** The reference set must be authored from source while no agent output exists
  to contaminate it. This is a gate condition, not a sequencing preference: no `src/agent/` code is
  written until the 4a golden is locked.
- **4a gate.** Build the 4a agent against the locked golden, **run the eval suite, report the numbers
  sliced** (construct × terminal state, §4.5), and **ratify in chat before the next stage opens.**
- **4c gate** (the next stage after 4a — per the §1 ordering lock). 4c's contract is **LOCKED in §9
  of this document** and in `AGENT_CONTRACT.md` §6 (the live fixture-vs-live tool eval); it is built
  against that contract and ratified at its gate.
- **4b gate** — **only if 4b is ever built** (deferred, §1). Its report-composition contract is
  specified and ratified at *its* gate, not pre-committed here.

**Standing disciplines (every gate):**

- **One reviewable step per turn** — no running end-to-end across gates.
- **Update `docs/HANDOFF.md` and `docs/LEARNINGS.md` at every phase boundary** (and at any commit
  that changes a locked decision or the build state).
- **Append to `docs/ENGINEERING_DECISIONS.md` while the reasoning is fresh.** Candidate entries
  already visible: the **loop-ownership decision** (code-owned vs native function-calling, §5.2);
  and the **fixture-vs-live eval call** when 4c arrives.

---

## 9. Phase 4C Contract — Live Tools (LOCKED)

The 4c design, locked before any client code. Scope: add a live clinical/regulatory layer that
answers what the static corpus structurally cannot, **without weakening the corpus-grounded
guarantees 4a established.** The eval-side additions (live golden, fixtures, provenance, route field,
value atom) are specified in `AGENT_CONTRACT.md` §6; this section owns the *agent / tool* design.

### 9.1 Go-live decision — corpus-first, absence-driven gap-fill only

- **Corpus-first invariant.** The corpus stays the primary source. A live call is made **only to
  fill a gap the corpus could not** — live lookups are **absence-driven gap-fills**, never the first
  move and never a parallel/duplicate path over content the corpus already answers.
- **No staleness / freshness mechanism — explicitly RULED OUT.** The agent does **not** call a live
  tool to "refresh" a fact the corpus already supplies. Ruled out on two grounds: (1) the public APIs
  in scope expose **no clean as-of/freshness signal** to compare a corpus fact against, and (2)
  corpus coverage does not make a staleness re-check worth a request. The live trigger is **absence**
  (the fact is missing), not **age** (the fact might be old) — a code-checkable condition, not a
  model judgement about currency.
- **ASSESS emits a closed-set gap-kind.** The ASSESS verdict's gap signal carries a **gap-kind from a
  closed set `{corpus, trial_status, regulatory_status}`**. **Code maps kind → tool and owns
  dispatch** — `trial_status → clinicaltrials_lookup`, `regulatory_status → fda_lookup`, `corpus →`
  the existing `corpus_retrieve` loop. The model **names the kind of gap; it does not choose or call
  the tool** — tool selection stays a refused knob *in the model* (§6); the choice is a **code branch
  over a closed enum**, exactly as terminal-state assignment is. This keeps 4c on the same
  code-owned-control-flow discipline as §5.2.

### 9.2 Tools — exactly two

- **`clinicaltrials_lookup`** — ClinicalTrials.gov **v2** API (trial / recruitment status, phase).
- **`fda_lookup`** — **openFDA only** (approvals, regulatory actions). **NOT EMA** — openFDA does not
  serve EMA data and EMA is out of scope for Phase 4 (this also corrects an earlier "FDA / EMA"
  reference in `src/tools/CLAUDE.md`).

### 9.3 Failure handling — no new terminal state

- **Tool failure degrades to refusal, not a crash.** A failed live call returns a **typed failed
  result** → contributes **empty evidence** → the **existing `insufficient_evidence` terminal state**
  (§2.3 / §5.5). **No new terminal state is introduced.**
- **Failure is recorded in the trajectory** (§2.5) so the eval can **distinguish a tool-failure cause
  from a genuine corpus-/record-absence** — both end in `insufficient_evidence`, but the receipts say
  which.
- **Caught conditions:** request **timeout**, **HTTP-error** status, and **malformed/unparseable
  body**. Each maps to the typed failed result.
- **No retries.** A failed call is not re-issued; the loop relies on the **existing hard iteration
  cap (§5.6)** and the **§5.5 state machine** (the exhausted / empty-evidence path already routes to
  `insufficient_evidence`). No new budget mechanism is added.
- **No cross-tool fallback.** A `trial_status` failure does **not** silently fall back to
  `fda_lookup` (or vice-versa); the §9.1 mapping is fixed.
- **openFDA key from env, absence is non-fatal.** The optional openFDA API key is read from the
  environment (never hardcoded); **its absence is not an error** — openFDA serves keyless at a lower
  rate limit, and the eval runs keyless regardless (`AGENT_CONTRACT.md` §6.5).
- **Failure handling is covered by unit tests** (a typed-failed-result on each caught condition),
  **not by a failure fixture or a golden eval entry** — the live golden scores answered/escalation
  behavior, while failure modes are a unit-test concern.
