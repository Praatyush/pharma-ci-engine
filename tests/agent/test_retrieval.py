"""Phase 4A Batch-5 tests — corpus_retrieve (the §5.3 tool) + the §5.7 index→span resolution layer.

corpus_retrieve's union/dedup/chunk-text logic is tested on mock legs (deterministic) AND, when the
real corpus + indexes are present, smoke-tested on the actual Phase 3 retriever. resolve_citations is
unit-tested, and the end-to-end test proves the agent loop (stubbed reasoning) → resolve → a
ResolvedAnswerObject the BATCH-2 SCORER consumes — the first time the agent's output meets the scorer.
"""

import pytest

from src.agent.loop import run_agent
from src.agent.resolve import resolve_citations
from src.agent.retrieval import CorpusRetriever, corpus_retrieve
from src.agent.types import AssessVerdict, EvidenceItem, PlanOutput, SynthesizeOutput
from src.evals import agent_metrics as M
from src.evals.answer_object import AnswerObject, Claim, ResolvedAnswerObject
from src.rag.units import RetrievalUnit

NOV = "q1-2026-interim-financial-report-en"


def ru(a, b, text, doc="d"):
    return RetrievalUnit(doc_id=doc, line_range=(a, b), text=text)


def ei(doc, lr, text="t"):
    return EvidenceItem(text=text, doc_id=doc, line_range=lr)


class MockLeg:
    """Stands in for ChunkLegRetriever / EntityLegRetriever: .units + .retrieve(query, k) -> [(unit, score)]."""

    def __init__(self, units):
        self.units = list(units)

    def retrieve(self, query, k):
        return [(u, 1.0 / (i + 1)) for i, u in enumerate(self.units)][:k]


class StubLLM:
    def __init__(self, plan, verdicts, synths):
        self._plan, self._verdicts, self._synths = plan, list(verdicts), list(synths)
        self.ai = self.si = 0

    def plan(self, question):
        return self._plan

    def assess(self, question, evidence):
        v = self._verdicts[self.ai]; self.ai += 1; return v

    def synthesize(self, question, evidence):
        o = self._synths[self.si]; self.si += 1; return o


class StubRetriever:
    def __init__(self, items):
        self._items = items

    def retrieve(self, sub_queries):
        return list(self._items)


# --------------------------------------------------------------------------- #
# corpus_retrieve (§5.3): chunk@10 ∪ fused@10, ≤20, deduped, chunk text
# --------------------------------------------------------------------------- #
def test_corpus_retrieve_union_dedup_and_chunk_text_mock():
    chunk = MockLeg([ru(2 * i + 1, 2 * i + 2, f"chunk text {i}") for i in range(12)])   # chunks 0..11
    # entity units co-located (same spans) with chunks 1, 2, 11 — but carrying DIFFERENT (serialized) text.
    entity = MockLeg([ru(3, 4, "ENTITY a"), ru(5, 6, "ENTITY b"), ru(23, 24, "ENTITY c")])

    out = corpus_retrieve("q", chunk, entity)
    spans = [(it.doc_id, it.line_range) for it in out]
    chunk_text = {(u.doc_id, u.line_range): u.text for u in chunk.units}

    assert len(out) <= 20                                   # ≤20 (10 ∪ 10)
    assert len(spans) == len(set(spans))                    # deduped on (doc_id, line_range)
    assert len(out) < 20                                    # chunk@10 and fused@10 overlap -> dedup actually happened
    # chunk@10 ⊆ union (the backbone's top-10 is all present, incl. (19,20) that fusion dropped)
    assert {(u.doc_id, u.line_range) for u in chunk.units[:10]} <= set(spans)
    assert ("d", (19, 20)) in spans                         # chunk-leg unique contribution (chunk 9)
    # fused@10 contributes a span NOT in chunk@10: chunk 11 (23,24), boosted into fusion by its entity co-location
    assert ("d", (23, 24)) in spans                         # fused-leg contribution beyond chunk@10
    # §5.3 each item carries CHUNK text (not the entity serialized text), keyed by its span
    assert all((it.doc_id, it.line_range) in chunk_text for it in out)
    assert all(it.text == chunk_text[(it.doc_id, it.line_range)] for it in out)
    assert next(it for it in out if it.line_range == (23, 24)).text == "chunk text 11"  # chunk text, not "ENTITY c"


def test_corpus_retriever_seam_fans_out_and_unions_by_span():
    chunk = MockLeg([ru(1, 2, "c1"), ru(3, 4, "c2")])
    entity = MockLeg([ru(3, 4, "e1")])
    out = CorpusRetriever(chunk, entity).retrieve(["sub-q-1", "sub-q-2"])   # two sub-queries, same corpus
    spans = [(it.doc_id, it.line_range) for it in out]
    assert len(spans) == len(set(spans))                    # unioned by span across sub-queries (no dup)
    assert set(spans) == {("d", (1, 2)), ("d", (3, 4))}


def test_corpus_retrieve_real_smoke():
    try:
        from src.agent.retrieval import build_corpus_retriever
        cr = build_corpus_retriever()
        items = corpus_retrieve("What is the approval status of Vanrafia in IgA nephropathy?", cr.chunk, cr.entity)
    except Exception as exc:                                 # corpus/indexes/embedding model not available here
        pytest.skip(f"real retriever unavailable: {type(exc).__name__}: {exc}")
    spans = [(it.doc_id, it.line_range) for it in items]
    assert 1 <= len(items) <= 20                             # ≤20 (§5.3)
    assert len(spans) == len(set(spans))                    # deduped
    assert all(it.text.strip() for it in items)             # chunk text present
    chunk_spans = {(u.doc_id, u.line_range) for u in cr.chunk.units}
    assert all((it.doc_id, it.line_range) in chunk_spans for it in items)   # every union span is a real chunk span


# --------------------------------------------------------------------------- #
# resolve_citations (§5.7): evidence index -> span
# --------------------------------------------------------------------------- #
def test_resolve_citations_maps_indices_to_spans():
    table = [ei("d", (1, 1)), ei("d", (2, 2)), ei("d", (3, 3)), ei("d", (4, 4))]
    ans = AnswerObject(question_id="Q", terminal_state="answered",
                       claims=[Claim(subject="s", attribute="a", value="v", citations=[1, 3])])
    res = resolve_citations(ans, table)
    assert isinstance(res, ResolvedAnswerObject)
    assert res.question_id == "Q" and res.terminal_state == "answered"
    assert [(s.doc_id, s.line_range) for s in res.claims[0].citations] == [("d", (2, 2)), ("d", (4, 4))]


def test_resolve_citations_shared_dedup_index_resolves_consistently():
    # a span retrieved twice -> ONE index in the table; two claims both citing it both resolve correctly
    table = [ei("d", (5, 5)), ei("d", (6, 6))]
    ans = AnswerObject(question_id="Q", terminal_state="answered", claims=[
        Claim(subject="s1", attribute="a", value="v", citations=[0]),
        Claim(subject="s2", attribute="a", value="v", citations=[0]),
    ])
    res = resolve_citations(ans, table)
    assert res.claims[0].citations[0].line_range == (5, 5)
    assert res.claims[1].citations[0].line_range == (5, 5)


def test_resolve_citations_out_of_range_raises():
    table = [ei("d", (1, 1))]
    ans = AnswerObject(question_id="Q", terminal_state="answered",
                       claims=[Claim(subject="s", attribute="a", value="v", citations=[5])])
    with pytest.raises(IndexError):
        resolve_citations(ans, table)


def test_loop_validation_prevents_out_of_range_at_resolution():
    # §5.8 integration: an out-of-range-citing claim is DROPPED at validation, so the emitted answer
    # carries no out-of-range index, and resolve_citations succeeds on the survivors.
    good = Claim(subject="g", attribute="a", value="v", citations=[0])
    oob = Claim(subject="x", attribute="y", value="z", citations=[99])   # 99 out of range (1 evidence item)
    llm = StubLLM(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")],
                  [SynthesizeOutput(claims=[good, oob]), SynthesizeOutput(claims=[good, oob])])
    res = run_agent("Q?", llm=llm, retriever=StubRetriever([ei("d", (1, 1))]))
    assert res.answer.terminal_state == "partially_answered"
    n = len(res.trajectory.evidence)
    assert all(0 <= i < n for c in res.answer.claims for i in c.citations)   # no out-of-range survived
    resolved = resolve_citations(res.answer, res.trajectory.evidence)        # must NOT raise
    assert resolved.claims[0].citations[0].line_range == (1, 1)


# --------------------------------------------------------------------------- #
# End-to-end: stubbed-LLM loop -> resolve -> ResolvedAnswerObject scored by the Batch-2 scorer
# --------------------------------------------------------------------------- #
def test_end_to_end_stubbed_llm_to_scoreable_resolved_answer():
    golden_q = {
        "expected_terminal_state": "answered",
        "reference_claims": [{
            "claim_id": "Q1-c1", "subject": "Vanrafia",
            "attribute": "approval status in IgA nephropathy", "value": "approved 2025 (US and China)",
            "acceptable_spans": [{"doc_id": NOV, "line_range": [443, 445]}],
        }],
    }
    # retriever hands the agent ONE evidence item = Q1's acceptable span (index 0)
    retriever = StubRetriever([ei(NOV, (443, 445), "Vanrafia ... approved 2025 in the US and China ...")])
    # stubbed reasoning: PLAN one sub-query; ASSESS sufficient; SYNTHESIZE the Q1 claim citing evidence index 0
    syn = SynthesizeOutput(claims=[Claim(subject="Vanrafia", attribute="approval status in IgA nephropathy",
                                         value="approved 2025 (US and China)", citations=[0])])
    llm = StubLLM(PlanOutput(sub_queries=["Vanrafia IgA nephropathy approval"]),
                  [AssessVerdict(kind="sufficient")], [syn])

    res = run_agent("What is the approval status of Vanrafia in IgA nephropathy?",
                    llm=llm, retriever=retriever, question_id="Q1")
    assert res.answer.terminal_state == "answered"

    # the §5.7 resolution layer: index -> span
    resolved = resolve_citations(res.answer, res.trajectory.evidence)
    assert isinstance(resolved, ResolvedAnswerObject)
    assert resolved.claims[0].citations[0].doc_id == NOV
    assert resolved.claims[0].citations[0].line_range == (443, 445)

    # ...and the Batch-2 scorer consumes it (oracle-equivalent on a matched, faithfully-cited claim)
    assert M.terminal_state_correct(resolved, golden_q) is True
    assert M.claim_recall(resolved, golden_q).recall == 1.0
    assert M.claim_precision(resolved, golden_q).precision == 1.0
    assert M.citation_faithfulness(resolved, golden_q).faithfulness == 1.0
