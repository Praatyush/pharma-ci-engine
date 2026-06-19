"""Unit tests for the agent CLI (src/agent/run.py) — CI-safe (no corpus, no key, no network).

Two tests: (1) ``_format_result`` rendering, driven by the REAL ``run_agent`` over inline stub
seams (mirroring tests/agent/test_retrieval.py); (2) ``main()`` wiring, with the live builders +
``run_agent`` monkeypatched (mirroring the monkeypatch precedent in tests/extraction/). Everything
real is stubbed or patched, so nothing touches data/, a model key, or the network.
"""

import sys

import src.agent.run as run
from src.agent.loop import run_agent
from src.agent.run import _format_result
from src.agent.types import AssessVerdict, EvidenceItem, PlanOutput, SynthesizeOutput
from src.evals.answer_object import Claim


# --- inline stubs (re-declared per file, as the existing tests/agent/ files do) ---
def ei(doc, lr, text="t"):
    return EvidenceItem(text=text, doc_id=doc, line_range=lr)


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
# TEST 1 — _format_result output (keyless, networkless): cited-claim + no-claim cases
# --------------------------------------------------------------------------- #
def test_format_result_renders_claims_and_empty_line():
    # (a) a result WITH a synthesized, cited claim
    retriever = StubRetriever([ei("novartis", (443, 445), "Vanrafia ... approved 2025 ...")])
    syn = SynthesizeOutput(claims=[Claim(subject="Vanrafia", attribute="approval status",
                                         value="approved 2025", citations=[0])])
    llm = StubLLM(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")], [syn])
    result = run_agent("What is the approval status of Vanrafia?", llm=llm, retriever=retriever)
    out = _format_result("What is the approval status of Vanrafia?", result)
    assert "TERMINAL STATE: answered" in out
    assert "Vanrafia" in out and "approval status" in out and "approved 2025" in out
    assert "(novartis, (443, 445))" in out                      # resolved (doc_id, line_range) citation

    # (b) a result with NO surviving claim (empty synthesis -> insufficient_evidence)
    retriever2 = StubRetriever([ei("d", (1, 1))])
    llm2 = StubLLM(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")],
                   [SynthesizeOutput(claims=[])])
    result2 = run_agent("Q?", llm=llm2, retriever=retriever2)
    out2 = _format_result("Q?", result2)
    assert "TERMINAL STATE: insufficient_evidence" in out2
    assert "CLAIMS: none" in out2


# --------------------------------------------------------------------------- #
# TEST 2 — main() wiring (monkeypatched; no live model / corpus / network)
# --------------------------------------------------------------------------- #
def test_main_wiring(monkeypatch, capsys):
    # Build a real fixture result via the stubbed loop (avoids hand-building the frozen Trajectory).
    fixture = run_agent(
        "ignored",
        llm=StubLLM(PlanOutput(sub_queries=["q"]), [AssessVerdict(kind="sufficient")],
                    [SynthesizeOutput(claims=[Claim(subject="s", attribute="a", value="v", citations=[0])])]),
        retriever=StubRetriever([ei("d", (1, 1))]),
    )
    calls = {}

    def fake_run_agent(question, **kwargs):
        calls["question"] = question
        calls.update(kwargs)
        return fixture

    monkeypatch.setattr(run, "build_corpus_retriever", lambda *a, **k: object())   # no data/ load
    monkeypatch.setattr(run, "GeminiLLMSeam", lambda *a, **k: object())            # no real client
    monkeypatch.setattr(run, "run_agent", fake_run_agent)                          # no live loop
    monkeypatch.setattr(sys, "argv", ["prog", "some question", "--max-iterations", "2"])

    run.main()
    out = capsys.readouterr().out

    assert calls["question"] == "some question"
    assert calls["max_iterations"] == 2
    assert calls["question_id"] == "?"                          # argparse default flows through
    assert fixture.answer.terminal_state in out                # main() formatted + printed the result
