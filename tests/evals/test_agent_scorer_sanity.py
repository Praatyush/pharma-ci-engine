"""Phase 4A scorer TRUST GATE (Batch 3) — six known-output sanity agents x the Batch-2 metrics.

Each sanity agent is a single fixture function returning a hardcoded ``ResolvedAnswerObject`` per
golden question (resolved spans directly — the evidence-index layer is out of baseline scope,
AGENT_CONTRACT §2). Running them through the four metrics (``src/evals/agent_metrics.py``) must
reproduce a pre-DERIVED expected-score matrix; an assertion failure means the SCORER is wrong, not the
expected value. NOT a pluggable runner/registry — just six functions and a matrix of asserts.

The sixth agent, ``OVER_BROAD``, was added with the Batch-6a faithfulness-direction correction
(`acceptable_span ⊆ agent_span`): it cites a document-spanning span and is therefore (by design)
scored FAITHFUL — making the flip's one false-positive explicit (out of scope for the real agent,
whose corpus_retrieve emits single-chunk spans). The derived expected matrix (with reasons) is printed
by ``__main__``; see the Batch-3 / 6a reports.
"""

import json
from pathlib import Path

from src.evals import agent_metrics as M
from src.evals.answer_object import ResolvedAnswerObject, ResolvedClaim, Span

_GOLDEN = json.loads(Path("src/evals/golden/agent.golden.json").read_text())
GOLDEN = _GOLDEN["questions"]

NOV = "q1-2026-interim-financial-report-en"
TAK = "qr2025_q4_Pipeline_table_en"

ANS = [f"Q{i}" for i in range(1, 10)]   # answered, claim-bearing
PAR = ["P1", "P3"]                       # partially_answered, claim-bearing
INS = ["I2", "I3"]                       # insufficient_evidence, claim-free


# --------------------------------------------------------------------------- #
# Sanity agents (fixtures) — each: golden_question dict -> ResolvedAnswerObject
# --------------------------------------------------------------------------- #
def _spans(ref) -> list[Span]:
    return [Span(doc_id=s["doc_id"], line_range=(s["line_range"][0], s["line_range"][1]))
            for s in ref["acceptable_spans"]]


def agent_oracle(gq) -> ResolvedAnswerObject:
    """Golden's exact reference claims (subject/attribute/value verbatim) cited to their exact
    acceptable_spans; golden's expected_terminal_state. Insufficient-expected -> insufficient, no claims."""
    claims = [ResolvedClaim(subject=r["subject"], attribute=r["attribute"], value=r["value"],
                            citations=_spans(r)) for r in gq["reference_claims"]]
    return ResolvedAnswerObject(question_id=gq["question_id"],
                                terminal_state=gq["expected_terminal_state"], claims=claims)


def agent_null(gq) -> ResolvedAnswerObject:
    """Always insufficient_evidence, no claims."""
    return ResolvedAnswerObject(question_id=gq["question_id"], terminal_state="insufficient_evidence", claims=[])


def agent_citation_failure(gq) -> ResolvedAnswerObject:
    """Oracle claims (correct subject/attribute/value/terminal_state) but every citation shifted FAR
    outside its acceptable span (same doc, +100000 lines) -> unfaithful."""
    o = agent_oracle(gq)
    claims = [ResolvedClaim(subject=c.subject, attribute=c.attribute, value=c.value,
                            citations=[Span(doc_id=s.doc_id, line_range=(s.line_range[0] + 100000, s.line_range[1] + 100000))
                                       for s in c.citations])
              for c in o.claims]
    return ResolvedAnswerObject(question_id=o.question_id, terminal_state=o.terminal_state, claims=claims)


def agent_hallucination(gq) -> ResolvedAnswerObject:
    """Oracle everywhere, plus on Q1 two fabricated claims exercising BOTH precision behaviors:
    (a) matches a golden (subject, attribute) but with a BAD citation -> in the denominator, fails;
    (b) a (subject, attribute) ABSENT from the golden -> excluded as n_unlisted (not penalized)."""
    o = agent_oracle(gq)
    if gq["question_id"] != "Q1":
        return o
    fab_a = ResolvedClaim(subject="Vanrafia", attribute="approval status in IgA nephropathy",
                          value="Filed (2025)",  # matched (subject, attribute); value irrelevant to precision
                          citations=[Span(doc_id=NOV, line_range=(100443, 100445))])  # BAD citation
    fab_b = ResolvedClaim(subject="Imaginarib", attribute="market share in atopic dermatitis",
                          value="Phase III",  # (subject, attribute) absent from the golden -> unlisted
                          citations=[Span(doc_id=NOV, line_range=(443, 445))])
    return ResolvedAnswerObject(question_id="Q1", terminal_state="answered", claims=[*o.claims, fab_a, fab_b])


def agent_overclaim(gq) -> ResolvedAnswerObject:
    """Oracle everywhere EXCEPT the insufficient-expected questions, where it confabulates an
    ANSWERED response with a faithfully-cited claim about real PV / recruitment spans."""
    qid = gq["question_id"]
    if qid not in INS:
        return agent_oracle(gq)
    if qid == "I2":  # Merck PV -> answer using real Jakavi PV content (distractor)
        claim = ResolvedClaim(subject="Jakavi", attribute="polycythemia vera presence",
                              value="marketed for PV", citations=[Span(doc_id=NOV, line_range=(4422, 4454))])
    else:            # I3 oveporexton recruitment -> transfer a real recruitment-status distractor
        claim = ResolvedClaim(subject="oveporexton", attribute="recruitment status",
                              value="actively recruiting", citations=[Span(doc_id=TAK, line_range=(15, 15))])
    return ResolvedAnswerObject(question_id=qid, terminal_state="answered", claims=[claim])


def agent_over_broad(gq) -> ResolvedAnswerObject:
    """Oracle's correct claims, but each cites a span FAR LARGER than any chunk — a document-spanning
    (0, 100000) span that swallows the golden span.

    Under the corrected faithfulness direction (`acceptable_span ⊆ agent_span`, §3.4) this is FAITHFUL:
    the blessed span is contained in the giant span. This is the one degenerate FALSE-POSITIVE of the
    swapped direction, made EXPLICIT here rather than left silent. It is OUT OF SCOPE for the real agent
    — `corpus_retrieve` emits only single-chunk-bounded spans, so a document-spanning citation cannot
    arise (the boundedness assumption the contract relies on)."""
    o = agent_oracle(gq)
    claims = [
        ResolvedClaim(subject=c.subject, attribute=c.attribute, value=c.value,
                      citations=[Span(doc_id=ref["acceptable_spans"][0]["doc_id"], line_range=(0, 100000))])
        for c, ref in zip(o.claims, gq["reference_claims"])
    ]
    return ResolvedAnswerObject(question_id=o.question_id, terminal_state=o.terminal_state, claims=claims)


AGENTS = {
    "NULL": agent_null,
    "ORACLE": agent_oracle,
    "CITATION_FAILURE": agent_citation_failure,
    "HALLUCINATION": agent_hallucination,
    "OVERCLAIM": agent_overclaim,
    "OVER_BROAD": agent_over_broad,
}


# --------------------------------------------------------------------------- #
# Derived expected-score matrix (HARDCODED from reasoning, NOT recomputed)
# --------------------------------------------------------------------------- #
def expected(agent: str, qid: str) -> dict:
    insuff = qid in INS
    # claim-bearing baseline, overwritten per agent
    e = dict(terminal_ok=None, recall=None, recall_m=None, precision=None, precision_m=None,
             n_unlisted=0, faithful=None, faithful_m=None, insuff_pass=None)
    if agent == "NULL":
        e["terminal_ok"] = insuff                       # null says insufficient -> only right on INS
        if insuff:
            e.update(recall_m=False, precision_m=False, faithful_m=False, insuff_pass=True)
        else:
            e.update(recall=0.0, recall_m=True, precision=None, precision_m=True, faithful=None, faithful_m=True)
    elif agent == "ORACLE":
        e["terminal_ok"] = True
        if insuff:
            e.update(recall_m=False, precision_m=False, faithful_m=False, insuff_pass=True)
        else:
            e.update(recall=1.0, recall_m=True, precision=1.0, precision_m=True, faithful=1.0, faithful_m=True)
    elif agent == "CITATION_FAILURE":
        e["terminal_ok"] = True
        if insuff:
            e.update(recall_m=False, precision_m=False, faithful_m=False, insuff_pass=True)
        else:
            e.update(recall=1.0, recall_m=True, precision=0.0, precision_m=True, faithful=0.0, faithful_m=True)
    elif agent == "HALLUCINATION":
        e["terminal_ok"] = True
        if insuff:
            e.update(recall_m=False, precision_m=False, faithful_m=False, insuff_pass=True)
        elif qid == "Q1":
            e.update(recall=1.0, recall_m=True, precision=0.5, precision_m=True, n_unlisted=1, faithful=0.5, faithful_m=True)
        else:
            e.update(recall=1.0, recall_m=True, precision=1.0, precision_m=True, faithful=1.0, faithful_m=True)
    elif agent == "OVERCLAIM":
        if insuff:
            e.update(terminal_ok=False, recall_m=False, precision_m=False, faithful_m=False, insuff_pass=False)
        else:
            e.update(terminal_ok=True, recall=1.0, recall_m=True, precision=1.0, precision_m=True, faithful=1.0, faithful_m=True)
    elif agent == "OVER_BROAD":
        # Same scores as ORACLE: the document-spanning citation CONTAINS the golden span, so under the
        # corrected direction (acc ⊆ agent) it is FAITHFUL -> precision/faithfulness 1.0. This is the
        # flip's one false-positive (an over-broad citation passes), explicit and out of scope for the
        # real agent (corpus_retrieve emits single-chunk spans only).
        e["terminal_ok"] = True
        if insuff:
            e.update(recall_m=False, precision_m=False, faithful_m=False, insuff_pass=True)
        else:
            e.update(recall=1.0, recall_m=True, precision=1.0, precision_m=True, faithful=1.0, faithful_m=True)
    return e


def _score(ao, gq):
    rr = M.claim_recall(ao, gq)
    pr = M.claim_precision(ao, gq)
    ff = M.citation_faithfulness(ao, gq)
    return dict(
        terminal_ok=M.terminal_state_correct(ao, gq),
        recall=rr.recall, recall_m=rr.meaningful,
        precision=pr.precision, precision_m=pr.meaningful, n_unlisted=pr.n_unlisted,
        faithful=ff.faithfulness, faithful_m=ff.meaningful,
        insuff_pass=(M.insufficient_pass(ao, gq) if gq["question_id"] in INS else None),
    )


def test_scorer_trust_gate():
    for agent_name, fn in AGENTS.items():
        for gq in GOLDEN:
            qid = gq["question_id"]
            got = _score(fn(gq), gq)
            exp = expected(agent_name, qid)
            for key in ("terminal_ok", "recall", "recall_m", "precision", "precision_m",
                        "n_unlisted", "faithful", "faithful_m", "insuff_pass"):
                assert got[key] == exp[key], (
                    f"{agent_name} x {qid}: metric {key!r} got {got[key]!r}, expected {exp[key]!r}"
                )


if __name__ == "__main__":
    def fmt(v):
        if v is None:
            return "  -  "
        if isinstance(v, bool):
            return " T " if v else " F "
        return f"{v:.2f}"

    fails = 0
    for agent_name, fn in AGENTS.items():
        print(f"\n=== {agent_name} ===")
        print(f"{'q':4} {'term':>5} {'recall':>7} {'prec':>6} {'unl':>4} {'faith':>6} {'insuf':>6}   result")
        for gq in GOLDEN:
            qid = gq["question_id"]
            got = _score(fn(gq), gq)
            exp = expected(agent_name, qid)
            ok = all(got[k] == exp[k] for k in exp)
            fails += not ok
            ip = "" if got["insuff_pass"] is None else fmt(got["insuff_pass"])
            print(f"{qid:4} {fmt(got['terminal_ok']):>5} {fmt(got['recall']):>7} {fmt(got['precision']):>6} "
                  f"{got['n_unlisted']:>4} {fmt(got['faithful']):>6} {ip:>6}   {'PASS' if ok else 'FAIL <-'}")
    print(f"\nTRUST GATE: {'ALL PASS' if fails == 0 else f'{fails} CELL(S) FAILED'}")
    test_scorer_trust_gate()
    print("assert pass: test_scorer_trust_gate OK")
