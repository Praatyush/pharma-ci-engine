"""Phase 4A research-agent control loop + code-owned terminal-state machine (Batch 4).

``PLAN`` once → ``[retrieve → ASSESS]*`` → ``SYNTHESIZE`` or refuse, with a HARD max-iterations cap
(§5.4 / §5.6). The terminal state is ASSIGNED BY CODE from (ASSESS verdict kind, synthesis-validation
outcome, surviving-claim count) — never model-declared (§5.5). SYNTHESIZE validation + one-retry
degrade per §5.8. Evidence accumulates across iterations into a span-deduped numbered table (§5.7) —
a span retrieved twice keeps one stable index. The LLM and retriever are injected behind the
``types.LLMSeam`` / ``types.RetrieverSeam`` Protocols (the real retriever is
``src.agent.retrieval.CorpusRetriever``; the LLM seam remains stubbed pending Batch 6).

Verdict well-formedness: each ASSESS verdict is checked against its ``kind`` and a malformed verdict
RAISES :class:`MalformedVerdict` (loud, not silently ignored — the same fail-loud discipline as the
scorer's raise-on-unrecognized-value-shape). The required field-set per kind: ``sufficient`` carries none of the optional fields; ``gap`` requires
non-empty ``follow_up_sub_queries`` (load-bearing — drives the next iteration) and carries no ``gaps``
(``missing_slots`` is OPTIONAL — descriptive annotation only); ``exhausted`` requires named ``gaps``
(and no gap-only fields).
"""

from src.agent.tool_seam import LiveToolSeam
from src.agent.types import (
    AgentRunResult,
    AssessVerdict,
    EvidenceItem,
    IterationRecord,
    LLMSeam,
    PlanOutput,
    RetrieverSeam,
    SynthesisValidation,
    SynthesizeOutput,
    ToolSeam,
    Trajectory,
)
from src.evals.answer_object import AnswerObject, Claim
from src.tools.clinicaltrials import TrialRecord
from src.tools.fda import FdaApprovalRecord

# §5.6 — the cap MECHANISM exists from day one; the VALUE is deferred (set from observed eval
# behavior). PLACEHOLDER default; always overridable via the ``max_iterations`` parameter.
DEFAULT_MAX_ITERATIONS = 3


class MalformedVerdict(ValueError):
    """An ASSESS verdict whose fields are inconsistent with its ``kind`` — fail loud, never ignore."""


def _check_verdict_wellformed(v: AssessVerdict) -> None:
    """Raise :class:`MalformedVerdict` if the verdict's fields don't match its ``kind`` (§5.4)."""
    if v.kind == "sufficient":
        if v.missing_slots or v.follow_up_sub_queries or v.gaps:
            raise MalformedVerdict(
                "sufficient verdict must carry no missing_slots / follow_up_sub_queries / gaps")
    elif v.kind == "gap":
        if not v.follow_up_sub_queries:
            # load-bearing: it drives the next iteration. (missing_slots is OPTIONAL — descriptive
            # annotation, used for no control decision, so its absence must NOT raise.)
            raise MalformedVerdict("gap verdict requires non-empty follow_up_sub_queries")
        if v.gaps:
            raise MalformedVerdict("gap verdict must not carry the exhausted-only field 'gaps'")
    elif v.kind == "exhausted":
        if not v.gaps:
            raise MalformedVerdict("exhausted verdict requires non-empty gaps")
        if v.missing_slots or v.follow_up_sub_queries:
            raise MalformedVerdict("exhausted verdict must not carry gap-only fields")
    else:  # unreachable given the Literal, but stay loud
        raise MalformedVerdict(f"unknown verdict kind {v.kind!r}")


def _validate_claims(raw: SynthesizeOutput, n_evidence: int) -> tuple[list[Claim], list[tuple[Claim, str]]]:
    """§5.8 index-range + non-empty checks. Returns (valid, invalid-with-error-summary).

    A claim is invalid if any of subject/attribute/value is empty, or any citation index is outside
    ``[0, n_evidence)``. (An empty citation list is fine here — uncited claims are valid output and
    are scored as unsupported downstream, not dropped at synthesis.)
    """
    valid: list[Claim] = []
    invalid: list[tuple[Claim, str]] = []
    for c in raw.claims:
        errs: list[str] = []
        if not c.subject.strip():
            errs.append("empty subject")
        if not c.attribute.strip():
            errs.append("empty attribute")
        if not c.value.strip():
            errs.append("empty value")
        for idx in c.citations:
            if not (0 <= idx < n_evidence):
                errs.append(f"citation index {idx} out of range [0,{n_evidence})")
        if errs:
            invalid.append((c, "; ".join(errs)))
        else:
            valid.append(c)
    return valid, invalid


def _synthesize_with_repair(
    llm: LLMSeam, question: str, evidence: list[EvidenceItem],
) -> tuple[list[Claim], int, list[SynthesisValidation]]:
    """§5.8 — synthesize → validate → on any invalid claim, ONE retry → degrade (keep valid, drop
    invalid). Returns (surviving valid claims, n_dropped, validation events). The retry is a fresh
    re-call (real impl re-prompts with the named errors); the degrade applies to the retried output."""
    n = len(evidence)
    events: list[SynthesisValidation] = []

    raw = llm.synthesize(question, list(evidence))
    valid, invalid = _validate_claims(raw, n)
    events.append(SynthesisValidation(1, len(valid), len(invalid), tuple(e for _, e in invalid)))
    if not invalid:
        return valid, 0, events

    raw2 = llm.synthesize(question, list(evidence))   # one repair retry (stubbed re-call this batch)
    valid2, invalid2 = _validate_claims(raw2, n)
    events.append(SynthesisValidation(2, len(valid2), len(invalid2), tuple(e for _, e in invalid2)))
    return valid2, len(invalid2), events              # keep valid, drop invalid


def _accumulate(
    items: list[EvidenceItem],
    evidence: list[EvidenceItem],
    seen_spans: set[tuple[str, tuple[int, int] | None]],
) -> None:
    """Append new items to the §5.7 numbered evidence table, deduped on (doc_id, line_range) — a span
    (or a tool record identity) seen twice keeps ONE stable index. Shared by corpus AND tool evidence."""
    for item in items:
        key = (item.doc_id, item.line_range)
        if key not in seen_spans:
            seen_spans.add(key)
            evidence.append(item)


def _trial_to_evidence(t: TrialRecord) -> EvidenceItem:
    """A ClinicalTrials.gov record → record-identity EvidenceItem (doc_id ``ctgov:<NCT>``, NO line span)."""
    text = f"Trial {t.nct_id}: status={t.status}; phase={t.phase}; {t.title}"
    return EvidenceItem(text=text, doc_id=f"ctgov:{t.nct_id}", line_range=None)


def _approval_to_evidence(a: FdaApprovalRecord) -> EvidenceItem:
    """An openFDA Drugs@FDA record → record-identity EvidenceItem (doc_id ``openfda:<app_no>``, NO span)."""
    text = (f"FDA application {a.application_number}: {a.brand_name} ({a.generic_name}); "
            f"submission_status={a.submission_status}")
    return EvidenceItem(text=text, doc_id=f"openfda:{a.application_number}", line_range=None)


def _dispatch_tool(tools: ToolSeam, verdict: AssessVerdict) -> list[EvidenceItem]:
    """Absence-driven gap-fill (§9.1): CODE maps gap_kind → tool, looks up the identifier
    (``follow_up_sub_queries[0]`` — guaranteed non-empty by gap well-formedness), and maps each returned
    record to a record-identity EvidenceItem. The model named the gap-kind; the code picks the tool."""
    query = verdict.follow_up_sub_queries[0]
    if verdict.gap_kind == "trial_status":
        return [_trial_to_evidence(t) for t in tools.clinicaltrials_lookup(query)]
    return [_approval_to_evidence(a) for a in tools.fda_lookup(query)]   # regulatory_status


def run_agent(
    question: str,
    *,
    llm: LLMSeam,
    retriever: RetrieverSeam,
    tools: ToolSeam | None = None,
    question_id: str = "?",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> AgentRunResult:
    """Run the agent loop over one question. Pure w.r.t. the injected seams; no real I/O here.

    ``tools`` is the §9 live-tool seam; it defaults to the production :class:`LiveToolSeam` and is
    invoked ONLY on a ``gap`` whose ``gap_kind`` is ``trial_status`` / ``regulatory_status`` — so a
    corpus-only run (every existing caller, gap_kind defaulting to ``corpus``) never touches it."""
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")
    if tools is None:
        tools = LiveToolSeam()

    plan = llm.plan(question)
    sub_queries = list(plan.sub_queries)
    evidence: list[EvidenceItem] = []                       # the §5.7 numbered evidence table (span-deduped)
    seen_spans: set[tuple[str, tuple[int, int] | None]] = set()
    iterations: list[IterationRecord] = []
    final_verdict: AssessVerdict | None = None
    budget_hit = False

    # PLAN once → [retrieve → ASSESS]* (single-element plan is just the degenerate case).
    for i in range(max_iterations):
        retrieved = list(retriever.retrieve(list(sub_queries)))
        _accumulate(retrieved, evidence, seen_spans)       # corpus → §5.7 numbered table (deduped)
        verdict = llm.assess(question, list(evidence))
        _check_verdict_wellformed(verdict)            # loud-on-malformed (§5.4 field-set per kind)
        iterations.append(IterationRecord(i, tuple(sub_queries), tuple(retrieved), verdict))
        final_verdict = verdict
        if verdict.kind in ("sufficient", "exhausted"):
            break
        # gap → fill it, then CONTINUE so the next ASSESS re-judges with the new evidence in the table
        # (§9.1 absence-driven; §5.5 still owns the terminal state). A trial_status/regulatory_status
        # gap dispatches the named tool and injects record-identity evidence into the SAME table via the
        # SAME dedup; gap_kind == "corpus" (the default) is unchanged — re-query the corpus next iteration.
        if verdict.gap_kind in ("trial_status", "regulatory_status"):
            _accumulate(_dispatch_tool(tools, verdict), evidence, seen_spans)
        sub_queries = list(verdict.follow_up_sub_queries)   # corpus: re-query terms; tool: identifier reused
    else:
        budget_hit = True                              # cap reached with no terminal verdict (§5.6)

    # --- code-owned terminal-state machine (§5.5) ---
    synthesis: tuple[SynthesisValidation, ...] = ()
    if budget_hit:
        terminal, reason, claims = (
            "insufficient_evidence",
            f"budget cap reached ({max_iterations} iterations) without sufficient/exhausted",
            [],
        )
    elif not evidence:
        # §5.4: SYNTHESIZE never runs on nothing.
        terminal, reason, claims = (
            "insufficient_evidence",
            f"{final_verdict.kind} but no evidence — synthesis skipped (§5.4: never on nothing)",
            [],
        )
    else:
        valid, n_dropped, events = _synthesize_with_repair(llm, question, evidence)
        synthesis = tuple(events)
        if not valid:                                          # no surviving claims (incl. empty synthesis)
            terminal, reason, claims = "insufficient_evidence", "synthesis produced no surviving claims", []
        elif final_verdict.kind == "sufficient":
            terminal = "answered" if n_dropped == 0 else "partially_answered"
            reason = "sufficient + clean synthesis" if n_dropped == 0 else f"sufficient + {n_dropped} claim(s) dropped"
            claims = valid
        else:                                                  # exhausted with ≥1 surviving claim
            terminal, reason, claims = "partially_answered", "exhausted + surviving claim(s)", valid

    answer = AnswerObject(question_id=question_id, terminal_state=terminal, claims=claims)
    trajectory = Trajectory(
        question=question,
        plan=plan,
        iterations=tuple(iterations),
        synthesis=synthesis,
        evidence=tuple(evidence),
        terminal_state=terminal,
        transition_reason=reason,
        max_iterations=max_iterations,
        iterations_used=len(iterations),
        budget_hit=budget_hit,
    )
    return AgentRunResult(answer=answer, trajectory=trajectory)
