"""Evidence-index → span resolution (AGENT_PLAN §5.7).

The agent cites by **evidence index** (the model never sees doc_ids / line ranges — it can't fabricate
a span, only reference an integer into the numbered evidence list). ``resolve_citations`` is the
deterministic code step (AGENT_CONTRACT §2) that maps each claim's citation indices back to
``{doc_id, line_range}`` spans via the run's evidence table, producing the ``ResolvedAnswerObject`` the
scorer consumes. This is the layer the baseline scorer (Batch 2/3) deliberately bypassed.

The evidence table is the loop's accumulated, span-deduped numbered list (``Trajectory.evidence``);
indices align with what SYNTHESIZE was shown and what §5.8 validation checked, so a well-formed run
never carries an out-of-range index here (out-of-range claims are dropped at validation). This step is
still defensive: an out-of-range index raises loudly rather than silently mis-resolving.
"""

from src.agent.types import EvidenceItem
from src.evals.answer_object import AnswerObject, ResolvedAnswerObject, ResolvedClaim, Span


def resolve_citations(answer: AnswerObject, evidence_table: list[EvidenceItem]) -> ResolvedAnswerObject:
    """Map every claim's evidence-index citations to ``Span`` objects via ``evidence_table``."""
    n = len(evidence_table)
    resolved_claims: list[ResolvedClaim] = []
    for c in answer.claims:
        spans: list[Span] = []
        for idx in c.citations:
            if not (0 <= idx < n):
                raise IndexError(
                    f"citation index {idx} out of range [0,{n}) — a valid run drops such claims at "
                    "§5.8 validation before resolution")
            e = evidence_table[idx]
            spans.append(Span(doc_id=e.doc_id, line_range=e.line_range))
        resolved_claims.append(
            ResolvedClaim(subject=c.subject, attribute=c.attribute, value=c.value, citations=spans))
    return ResolvedAnswerObject(
        question_id=answer.question_id, terminal_state=answer.terminal_state, claims=resolved_claims)
