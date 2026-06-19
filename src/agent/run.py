"""CLI: ask the research agent one competitive-intelligence question (live).

    python -m src.agent.run "What is the approval status of Vanrafia in IgA nephropathy?"

Builds the committed Phase-3 corpus retriever + the real Gemini LLM seam, runs the
agent loop once (PLAN -> [retrieve -> ASSESS]* -> SYNTHESIZE), and prints the terminal
state plus each synthesized claim with its citations resolved to (doc_id, line_range).
Tools default to LIVE — ``run_agent`` builds ``LiveToolSeam`` itself, so escalation to
ClinicalTrials.gov / openFDA fires only on a gap the corpus cannot fill.

Requires LOCAL gitignored data (``data/reports/``, ``data/eval/extractions/``,
``data/rag/``) and ``GEMINI_API_KEY`` + ``GEMINI_MODEL`` in the environment
(``set -a; source .env; set +a``). Missing data or key fails loudly — there is no
offline / clean-clone mode.
"""

import argparse

from src.agent.gemini_seam import GeminiLLMSeam
from src.agent.loop import DEFAULT_MAX_ITERATIONS, run_agent
from src.agent.resolve import resolve_citations
from src.agent.retrieval import build_corpus_retriever


def _format_result(question: str, result) -> str:
    """Human-readable text: terminal state + each resolved claim (citations as (doc_id, line_range))."""
    resolved = resolve_citations(result.answer, list(result.trajectory.evidence))
    tr = result.trajectory
    lines = [
        f"QUESTION: {question}",
        f"TERMINAL STATE: {result.answer.terminal_state}",
        f"  ({tr.iterations_used} iteration(s); {tr.transition_reason})",
    ]
    if not resolved.claims:
        lines.append("CLAIMS: none (no claim synthesized).")
        return "\n".join(lines)
    lines.append(f"CLAIMS ({len(resolved.claims)}):")
    for i, claim in enumerate(resolved.claims, start=1):
        lines.append(f"  [{i}] subject:   {claim.subject}")
        lines.append(f"      attribute: {claim.attribute}")
        lines.append(f"      value:     {claim.value}")
        if claim.citations:
            for span in claim.citations:
                lines.append(f"      cite:      ({span.doc_id}, {span.line_range})")
        else:
            lines.append("      cite:      (uncited)")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="The competitive-intelligence question to ask.")
    parser.add_argument(
        "--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS,
        help="Hard cap on retrieve->ASSESS iterations (default: run_agent's default).")
    parser.add_argument(
        "--question-id", default="?", help="Optional id for the answer object (default: '?').")
    args = parser.parse_args()

    retriever = build_corpus_retriever()
    llm = GeminiLLMSeam(temperature=0.0)
    result = run_agent(
        args.question,
        llm=llm,
        retriever=retriever,
        question_id=args.question_id,
        max_iterations=args.max_iterations,
    )
    print(_format_result(args.question, result))


if __name__ == "__main__":
    main()
