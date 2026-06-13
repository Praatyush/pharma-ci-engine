# AGENT_CONTRACT.md — Phase 4 answer-object ↔ scorer interface (FROZEN)

> **Frozen interface contract** between the future research agent (which emits **answer-objects**)
> and the evaluation scorer (which consumes them against `src/evals/golden/agent.golden.json`). Both
> the agent and the scorer are built against this contract so they **cannot drift**. This is the
> **answer-object analogue** of what `agent.golden.json` froze for the golden side. Every decision
> here is already frozen in `docs/AGENT_PLAN.md` and the committed golden — this document only
> transcribes them into one reference page; it introduces no new design.

## 1. Answer-object schema (what the agent emits)

```
answer_object = {
  "question_id":   string,        # matches a golden question_id
  "terminal_state": "answered" | "partially_answered" | "insufficient_evidence",
  "claims": [                     # list; EMPTY for an insufficient_evidence answer
    {
      "subject":   string,        # open vocabulary — never an enum
      "attribute": string,        # open vocabulary — never an enum
      "value":     string,        # open vocabulary — never an enum
      "citations": [ int, ... ]   # evidence INDICES, not (doc_id, line_range)
    }
  ]
}
```

- `terminal_state` uses the **exact spelling/casing** of the golden's `expected_terminal_state`:
  `answered` | `partially_answered` | `insufficient_evidence`.
- `subject` / `attribute` / `value` are the three-slot open-string claim key (AGENT_PLAN §3) — open
  vocabulary, **never enums**.
- `citations` are **integer indices into the numbered evidence list the agent was shown**. The agent
  **never sees or emits `doc_id`s or line ranges.** Per AGENT_PLAN §5.7 this is the provenance
  mechanism: the model **structurally cannot fabricate a span** because it only ever references an
  integer index.

## 2. Resolved-answer-object (what the scorer consumes)

Identical to the answer-object **except** each citation is resolved from an evidence index to a
`{doc_id, line_range}` span:

```
resolved_claim.citations = [ { "doc_id": string, "line_range": [start_int, end_int] }, ... ]
```

- A **deterministic code step** — `resolve_citations(answer_object, evidence_table) →
  resolved_answer_object` — performs this mapping using the **run's evidence table** (part of the
  trajectory record), **before** scoring. The scorer operates on **resolved spans**, never on raw
  indices.
- **Baseline sanity-check agents emit resolved spans directly** (they bypass the index indirection,
  since no real evidence table exists yet). The **index→span resolution layer is tested separately at
  agent-integration time, not in the baseline.**

## 3. Scorer answer-level metrics (frozen definitions)

1. **`terminal_state_correct`** — exact enum match between the answer-object `terminal_state` and the
   golden `expected_terminal_state`. **Binary per question.**

2. **`claim_recall`** — fraction of golden `reference_claims` matched by some agent claim. A reference
   claim is **recalled iff** an agent claim matches on **normalized `(subject, attribute)` AND
   value-matches** (via the existing `normalize.py` machinery). **Separately tracked diagnostic:** any
   reference claim matched on `(subject, attribute)` but with a **WRONG value** is recorded apart and
   is **not folded into recall** — it localizes a *synthesis-misread* failure, distinct from a
   *not-found* failure.

3. **`claim_precision`** — fraction of agent claims that are **SUPPORTED**, where a claim is supported
   **iff ALL of its citations are faithful** (see metric 4). A claim with **zero citations is
   UNSUPPORTED** (an uncited claim is invalid — there are no confidence scores; uncited = unsupported).
   Precision penalizes **unsupported/hallucinated** claims, **NOT** true-but-unlisted claims (richness
   is governed by faithfulness, not by the reference set).

4. **`citation_faithfulness`** — **per-citation, binary containment.** An agent citation (resolved to
   a span) is **faithful iff** `acceptable_span ⊆ agent_span` — the blessed evidence region falls
   **within** the agent's cited span — for **at least one** of the golden claim's `acceptable_spans`
   (**OR semantics** across the list). Reuses `retrieval_scorer.line_containment` (operands swapped).
   **No threshold, no fractional credit.** Uncited claims are **absent from the faithfulness
   denominator** (they fail precision instead).

   > **Direction correction (revealed by the Batch-6a Q1 run; deliberate, documented change to a frozen
   > artifact).** The original rule was `agent_span ⊆ acceptable_span`, written when the trust-gate
   > oracle cited the *exact* golden spans. But the real agent cites at **chunk grain** — `corpus_retrieve`
   > returns chunk spans (e.g. `(432,486)`) — while the golden blesses **sub-chunk** spans (e.g.
   > `(443,445)`). Under the old rule a correct chunk citation that *contains* the blessed span was scored
   > unfaithful (it is broader than the sub-chunk span), demanding a granularity the agent never sees. The
   > corrected rule is therefore `acceptable_span ⊆ agent_span`. **Boundedness assumption:** this is sound
   > because `corpus_retrieve` guarantees **single-chunk-bounded** citations (chunk@10 ∪ fused@10, each a
   > single chunk), so an over-broad (e.g. document-spanning) citation cannot arise from the real agent —
   > the one degenerate false-positive of the swapped direction (a giant span trivially contains the
   > blessed span) is out of scope for the real agent and is made explicit by the `OVER-BROAD-CITATION`
   > sanity agent in the Batch-3 matrix.

## 4. Insufficient-evidence question rule

For a golden question whose `expected_terminal_state` is `insufficient_evidence` (`reference_claims`
is empty), the **pass criterion is**: `terminal_state == "insufficient_evidence"` **AND the agent
emitted ZERO claims**. **Any emitted claim is a failure REGARDLESS of its citation faithfulness** — a
faithfully-cited claim about the wrong subject (e.g. answering a Merck question using Jakavi PV
content) is **still a failure**, caught by terminal-state-correctness plus precision against an empty
reference set. On these questions, **`terminal_state_correct` is the load-bearing metric**;
`claim_precision` / `citation_faithfulness` are **not independently meaningful**.

## 5. Aggregation rule

Metrics are reported **sliced** (per-question, per-construct, per-terminal-state) and **NEVER bare**.
Claim metrics are aggregated **only WITHIN terminal-state strata** — there is **NO cross-stratum
claim-metric average** (averaging claim-recall across claim-bearing `answered`/`partially_answered`
questions and claim-free `insufficient_evidence` questions would be meaningless).

## 6. Phase 4C live-tool eval-contract additions (LOCKED)

The 4c eval additions, locked alongside `AGENT_PLAN.md` §9. **The frozen `agent.golden.json` is
unchanged** — every 4c entry lives in a **separate live golden** so the §1–§5 contract above cannot
drift.

### 6.1 Separate live golden

- **File:** `src/evals/golden/agent.golden.live.json`, **schema version `agent-golden-live-v1`**
  (distinct from the frozen `agent-golden-v1`). The frozen `agent.golden.json` is **not touched**.
- **Live slice — single-mode, `live_enabled` expectations only** (the corpus-only side of the story
  is already supplied by frozen-golden **I3**, so the live golden does not re-litigate corpus-only
  refusal):
  - **L1 — oveporexton recruitment status.** An **attribute-gap-with-distractor escalation**: the
    subject is in the corpus but the *recruitment-status attribute* is absent (and the corpus carries
    distractor recruitment language for other assets — cf. I3), so ASSESS escalates `trial_status` →
    `clinicaltrials_lookup`. **Anchored to a specific Completed ClinicalTrials.gov trial.**
  - **L2 — pitolisant / Wakix approval status.** A **clean entity-absence escalation**: the entity is
    wholly absent from the corpus (confirmed), so ASSESS escalates `regulatory_status` →
    `fda_lookup` (openFDA).
  - **one reused corpus control question** — a single-construct question the corpus answers, carried
    over to prove the live path does **not** fire when the corpus suffices (the corpus-first
    invariant, `AGENT_PLAN.md` §9.1, made measurable).

### 6.2 Tool-claim provenance — record-identity source form

A claim sourced from a live tool resolves its citation to a **record identity**, not a line span:

- **`doc_id`** is a **record-identity string**: `ctgov:<NCT id>` for ClinicalTrials.gov,
  `openfda:<application_no>` for openFDA.
- **`line_range` is `null`** for tool claims (there are no source lines — the unit is the record).
- **Citation faithfulness for tool claims is record-level containment** — the cited record identity
  must match the record that supports the claim. Corpus claims keep the §3.4 line-span containment;
  tool claims use record identity. The two provenance forms are **disjoint and never compared**.

### 6.3 `expected_route` — blessed-and-tested, not scored

Each live golden entry carries an **`expected_route`** (which tool/route the correct answer comes
through). It is a **blessed field asserted in the trust gate** (the test proves the code's kind→tool
dispatch reaches the expected tool), **NOT a scored or reported metric** — it does not enter
recall / precision / faithfulness or any sliced number. It guards **dispatch correctness** in the
gate; it is not part of the answer-quality score.

### 6.4 Value-layer canonicalizer — one new atom

- **One new atom** for **ClinicalTrials.gov `overallStatus`** (a controlled vocabulary — e.g.
  `RECRUITING` / `COMPLETED` / `TERMINATED` / …), added to the value-matching layer so live trial
  statuses canonicalize like the existing closed-set atoms.
- **openFDA `"approved"` reuses the EXISTING status atom** — no new atom; regulatory-approval status
  already canonicalizes through the Phase-4a value layer.

### 6.5 Fixture-vs-live — recorded responses, transport-mocked, keyless eval

- **Fixtures = recorded raw HTTP responses**, **committed under `src/evals/fixtures/`** (a tracked
  path — confirmed not swept by `.gitignore`, unlike `data/`).
- **Mocked at the httpx transport layer** via **`MockTransport`**; the **live/eval switch is an
  injected transport** (eval injects the fixture-backed transport; the live demo injects the real
  one). The client code is identical on both paths — only the transport differs.
- **Loud failure on an unexpected request** — a fixture transport that receives a request it has no
  recorded response for **raises**, so a test can never silently hit a path it did not record.
- **The eval is keyless and networkless** — it makes **no live calls** and needs **no openFDA key**
  (the key is **demo-only**, `AGENT_PLAN.md` §9.3).
- **Authoring discipline (two independent sources must agree).** Golden **values** are blessed from
  the **authoritative public record** (ClinicalTrials.gov / openFDA / FDA label); **fixtures** are
  captured **independently** from the API response. **The two must agree at record time** — a golden
  value and its fixture are cross-checked when authored, so a fixture cannot silently define its own
  ground truth.
