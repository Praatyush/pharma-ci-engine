"""Phase 4A agent control-loop + state-machine unit tests (Batch 4) — LLM/retriever fully STUBBED.

Drives ``src.agent.loop.run_agent`` with scripted stub outputs injected through the
``LLMSeam`` / ``RetrieverSeam`` Protocols — no real Gemini calls, no retriever. Asserts every §5.5
terminal-state branch, the §5.6 cap halt, the §5.8 validation/degrade, and the verdict-well-formedness
raise. This realizes §5.5's "unit-testable without API calls" property.
"""

import pytest

from src.agent.loop import DEFAULT_MAX_ITERATIONS, MalformedVerdict, run_agent
from src.agent.types import AssessVerdict, EvidenceItem, PlanOutput, SynthesizeOutput
from src.evals.answer_object import Claim


# --------------------------------------------------------------------------- #
# Builders + scripted stubs
# --------------------------------------------------------------------------- #
def ev(text="e", doc="d", lr=(1, 1)):
    return EvidenceItem(text=text, doc_id=doc, line_range=lr)


def claim(subject="s", attribute="a", value="v", citations=(0,)):
    return Claim(subject=subject, attribute=attribute, value=value, citations=list(citations))


def gap(slots=("stage",), follow=("q-next",)):
    return AssessVerdict(kind="gap", missing_slots=list(slots), follow_up_sub_queries=list(follow))


class StubLLM:
    def __init__(self, plan, verdicts, synths=()):
        self._plan, self._verdicts, self._synths = plan, list(verdicts), list(synths)
        self.assess_calls = 0
        self.synth_calls = 0

    def plan(self, question):
        return self._plan

    def assess(self, question, evidence):
        v = self._verdicts[self.assess_calls]
        self.assess_calls += 1
        return v

    def synthesize(self, question, evidence):
        o = self._synths[self.synth_calls]
        self.synth_calls += 1
        return o


class StubRetriever:
    def __init__(self, per_call):
        self._per_call, self.calls = list(per_call), 0

    def retrieve(self, sub_queries):
        out = self._per_call[self.calls] if self.calls < len(self._per_call) else []
        self.calls += 1
        return out


def _run(plan, verdicts, synths, *, retr, **kw):
    return run_agent("Q?", llm=StubLLM(plan, verdicts, synths), retriever=StubRetriever(retr), **kw)


# --------------------------------------------------------------------------- #
# Terminal-state branches (§5.5)
# --------------------------------------------------------------------------- #
def test_sufficient_to_answered():
    llm = StubLLM(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")],
                  [SynthesizeOutput(claims=[claim(citations=(0,))])])
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([[ev()]]), question_id="Q1")
    assert res.answer.terminal_state == "answered"
    assert res.answer.question_id == "Q1"
    assert len(res.answer.claims) == 1
    assert res.trajectory.iterations_used == 1 and res.trajectory.budget_hit is False
    assert llm.synth_calls == 1  # clean synthesis -> no retry
    assert res.trajectory.plan.sub_queries == ["q"]
    assert res.trajectory.iterations[0].verdict.kind == "sufficient"


def test_degenerate_single_subquery_is_not_a_special_path():
    res = _run(PlanOutput(sub_queries=["only-one"]), [AssessVerdict(kind="sufficient")],
               [SynthesizeOutput(claims=[claim()])], retr=[[ev()]])
    assert res.answer.terminal_state == "answered"
    assert len(res.trajectory.plan.sub_queries) == 1


def test_exhausted_with_claims_to_partially():
    res = _run(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="exhausted", gaps=["x"])],
               [SynthesizeOutput(claims=[claim()])], retr=[[ev()]])
    assert res.answer.terminal_state == "partially_answered"
    assert len(res.answer.claims) == 1


def test_sufficient_with_dropped_claim_to_partially():
    good, bad = claim(subject="good", citations=(0,)), claim(subject="bad", citations=(99,))  # 99 OOB (n=1)
    llm = StubLLM(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")],
                  [SynthesizeOutput(claims=[good, bad]),     # raw1: 1 invalid -> retry
                   SynthesizeOutput(claims=[good, bad])])    # raw2: still 1 invalid -> drop it
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([[ev()]]))
    assert res.answer.terminal_state == "partially_answered"
    assert [c.subject for c in res.answer.claims] == ["good"]   # only the valid claim survives
    assert llm.synth_calls == 2                                  # the one retry fired
    assert res.trajectory.synthesis[-1].n_dropped == 1


def test_empty_synthesis_to_insufficient():
    llm = StubLLM(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")],
                  [SynthesizeOutput(claims=[])])
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([[ev()]]))
    assert res.answer.terminal_state == "insufficient_evidence"
    assert res.answer.claims == []
    assert llm.synth_calls == 1   # empty IS valid output -> no retry, routes to insufficient


def test_exhausted_with_no_surviving_claims_to_insufficient():
    res = _run(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="exhausted", gaps=["x"])],
               [SynthesizeOutput(claims=[])], retr=[[ev()]])
    assert res.answer.terminal_state == "insufficient_evidence"


def test_terminal_state_is_code_assigned_not_model_declared():
    # ASSESS says sufficient, but synthesis is empty -> CODE assigns insufficient (verdict can't dictate it)
    res = _run(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")],
               [SynthesizeOutput(claims=[])], retr=[[ev()]])
    assert res.answer.terminal_state == "insufficient_evidence"


# --------------------------------------------------------------------------- #
# Budget cap (§5.6)
# --------------------------------------------------------------------------- #
def test_budget_cap_to_insufficient_and_halts():
    llm = StubLLM(PlanOutput(sub_queries=["q"]), [gap(follow=("q2",)), gap(follow=("q3",))], [])
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([[ev()], [ev()]]), max_iterations=2)
    assert res.answer.terminal_state == "insufficient_evidence"
    assert res.trajectory.budget_hit is True
    assert res.trajectory.iterations_used == 2          # halted exactly at the cap
    assert llm.assess_calls == 2 and llm.synth_calls == 0   # no SYNTHESIZE on budget cap
    assert res.answer.claims == []


def test_loop_stops_early_on_sufficient_before_cap():
    llm = StubLLM(PlanOutput(sub_queries=["q"]),
                  [gap(follow=("q2",)), AssessVerdict(kind="sufficient")],
                  [SynthesizeOutput(claims=[claim(citations=(0, 1))])])  # cites both accumulated items
    res = run_agent("Q?", llm=llm,
                    retriever=StubRetriever([[ev("a", lr=(1, 1))], [ev("b", lr=(2, 2))]]), max_iterations=5)
    assert res.answer.terminal_state == "answered"
    assert res.trajectory.iterations_used == 2 and res.trajectory.budget_hit is False   # stopped at 2, not 5
    assert len(res.trajectory.evidence) == 2            # two DISTINCT spans accumulated across iterations
    assert res.trajectory.iterations[1].sub_queries == ("q2",)   # the gap follow-up drove iteration 2


def test_loop_dedups_repeated_span_across_iterations():
    # the SAME span retrieved in iter 1 and iter 2 -> one stable slot in the numbered table (§5.7)
    same = ev("dup", doc="d", lr=(7, 7))
    llm = StubLLM(PlanOutput(sub_queries=["q"]),
                  [gap(follow=("q2",)), AssessVerdict(kind="sufficient")],
                  [SynthesizeOutput(claims=[claim(citations=(0,))])])
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([[same], [same]]), max_iterations=5)
    assert len(res.trajectory.evidence) == 1            # deduped across iterations
    assert res.answer.terminal_state == "answered"
    # the per-iteration record keeps the RAW retrieval (pre-dedup), both iterations saw the span
    assert res.trajectory.iterations[0].retrieved == (same,)
    assert res.trajectory.iterations[1].retrieved == (same,)


def test_default_max_iterations_is_the_cap():
    verdicts = [gap(follow=("q",)) for _ in range(DEFAULT_MAX_ITERATIONS)]
    llm = StubLLM(PlanOutput(sub_queries=["q"]), verdicts, [])
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([[ev()]] * DEFAULT_MAX_ITERATIONS))
    assert res.trajectory.iterations_used == DEFAULT_MAX_ITERATIONS and res.trajectory.budget_hit is True
    assert res.answer.terminal_state == "insufficient_evidence"


def test_max_iterations_must_be_positive():
    with pytest.raises(ValueError):
        run_agent("Q?", llm=StubLLM(PlanOutput(sub_queries=["q"]), [], []),
                  retriever=StubRetriever([]), max_iterations=0)


# --------------------------------------------------------------------------- #
# SYNTHESIZE validation / one-retry degrade (§5.8)
# --------------------------------------------------------------------------- #
def test_degrade_keeps_valid_drops_invalid():
    v1, v2 = claim(subject="v1", citations=(0,)), claim(subject="v2", citations=(0,))
    bad = claim(subject="bad", citations=(50,))   # OOB (n=1)
    llm = StubLLM(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")],
                  [SynthesizeOutput(claims=[v1, v2, bad]), SynthesizeOutput(claims=[v1, v2, bad])])
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([[ev()]]))
    assert res.answer.terminal_state == "partially_answered"
    assert sorted(c.subject for c in res.answer.claims) == ["v1", "v2"]
    last = res.trajectory.synthesis[-1]
    assert last.n_valid == 2 and last.n_dropped == 1


def test_repair_success_to_answered():
    good, bad = claim(subject="g", citations=(0,)), claim(subject="b", citations=(99,))
    llm = StubLLM(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")],
                  [SynthesizeOutput(claims=[good, bad]),   # raw1: 1 invalid -> retry
                   SynthesizeOutput(claims=[good])])        # raw2: clean -> answered (0 dropped)
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([[ev()]]))
    assert res.answer.terminal_state == "answered"
    assert llm.synth_calls == 2 and res.trajectory.synthesis[-1].n_dropped == 0


def test_invalid_only_synthesis_to_insufficient():
    bad = claim(subject="b", citations=(99,))
    llm = StubLLM(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")],
                  [SynthesizeOutput(claims=[bad]), SynthesizeOutput(claims=[bad])])  # both attempts all-invalid
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([[ev()]]))
    assert res.answer.terminal_state == "insufficient_evidence"   # 0 surviving claims


# --------------------------------------------------------------------------- #
# Verdict well-formedness — loud-on-malformed
# --------------------------------------------------------------------------- #
def test_malformed_sufficient_with_gap_fields_raises():
    bad = AssessVerdict(kind="sufficient", follow_up_sub_queries=["x"])
    with pytest.raises(MalformedVerdict):
        run_agent("Q?", llm=StubLLM(PlanOutput(sub_queries=["q"]), [bad],
                                    [SynthesizeOutput(claims=[claim()])]),
                  retriever=StubRetriever([[ev()]]))


def test_malformed_gap_without_followups_raises():
    # follow_up_sub_queries is load-bearing (drives the next iteration) -> its absence still raises
    bad = AssessVerdict(kind="gap", missing_slots=["stage"])   # has slots but NO follow_up_sub_queries
    with pytest.raises(MalformedVerdict):
        run_agent("Q?", llm=StubLLM(PlanOutput(sub_queries=["q"]), [bad], []),
                  retriever=StubRetriever([[ev()]]))


def test_gap_without_missing_slots_is_wellformed():
    # missing_slots is OPTIONAL (descriptive) -> a gap with follow-ups but no slots must NOT raise
    gap_no_slots = AssessVerdict(kind="gap", follow_up_sub_queries=["q2"])   # no missing_slots
    llm = StubLLM(PlanOutput(sub_queries=["q"]), [gap_no_slots, AssessVerdict(kind="sufficient")],
                  [SynthesizeOutput(claims=[claim(citations=(0, 1))])])
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([[ev("a", lr=(1, 1))], [ev("b", lr=(2, 2))]]))
    assert res.answer.terminal_state == "answered"
    assert res.trajectory.iterations[0].verdict.missing_slots == []   # recorded as-is (empty), didn't raise


def test_malformed_exhausted_missing_gaps_raises():
    bad = AssessVerdict(kind="exhausted")   # no gaps
    with pytest.raises(MalformedVerdict):
        run_agent("Q?", llm=StubLLM(PlanOutput(sub_queries=["q"]), [bad], []),
                  retriever=StubRetriever([[ev()]]))


def test_wellformed_verdicts_do_not_raise():
    # well-formed gap (named slots + follow-ups) then well-formed sufficient -> clean run
    res = _run(PlanOutput(sub_queries=["q"]),
               [gap(slots=("stage",), follow=("q2",)), AssessVerdict(kind="sufficient")],
               [SynthesizeOutput(claims=[claim(citations=(0, 1))])],
               retr=[[ev("a", lr=(1, 1))], [ev("b", lr=(2, 2))]])
    assert res.answer.terminal_state == "answered"
