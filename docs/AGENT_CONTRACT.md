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
   a span) is **faithful iff** `agent_span ⊆ acceptable_span` for **at least one** of the golden
   claim's `acceptable_spans` (**OR semantics** across the list). Reuses
   `retrieval_scorer.line_containment`. **No threshold, no fractional credit.** Uncited claims are
   **absent from the faithfulness denominator** (they fail precision instead).

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
