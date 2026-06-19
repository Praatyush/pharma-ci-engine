"""Real ``LLMSeam`` — the three agent calls (PLAN / ASSESS / SYNTHESIZE) as Gemini structured-output
calls, reusing the Phase 1 extraction setup verbatim (``extraction.gemini_client.generate_structured``;
same ``google-genai`` SDK, same ``GEMINI_API_KEY`` / ``GEMINI_MODEL`` env, same Flash-Lite model,
``temperature=0``). No new provider/model/abstraction.

Response-view models here are plain ``BaseModel`` (no ``extra="forbid"``) — mirroring
``extraction.models`` — because that is the shape the Gemini schema converter is proven to accept; the
seam then converts them into the frozen ``types.py`` schemas (``PlanOutput`` / ``AssessVerdict`` /
``SynthesizeOutput``). Prompts are written inline (prompt text is implementation, per AGENT_PLAN).

§5.7 provenance: SYNTHESIZE (and ASSESS) see a NUMBERED evidence list — ``[i] <text>`` — and never a
``doc_id`` or line range; claims cite by INTEGER INDEX into that list. Indices are 0-based, matching the
loop's evidence table, so ``resolve_citations`` maps them directly.
"""

from typing import Literal

from pydantic import BaseModel, Field

from src.agent.types import AssessVerdict, EvidenceItem, PlanOutput, SynthesizeOutput
from src.evals.answer_object import Claim
from src.extraction.gemini_client import generate_structured

# --------------------------------------------------------------------------- #
# Response-view models (plain BaseModel — the converter-safe shape; mirror extraction.models)
# --------------------------------------------------------------------------- #
class _PlanResponse(BaseModel):
    sub_queries: list[str] = Field(default_factory=list)


class _AssessResponse(BaseModel):
    kind: Literal["sufficient", "gap", "exhausted"]
    gap_kind: Literal["corpus", "trial_status", "regulatory_status"] = "corpus"
    missing_slots: list[str] = Field(default_factory=list)
    follow_up_sub_queries: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class _SynthClaim(BaseModel):
    subject: str
    attribute: str
    value: str
    citations: list[int] = Field(default_factory=list)


class _SynthResponse(BaseModel):
    claims: list[_SynthClaim] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Prompts (inline; tight, matched to the schemas)
# --------------------------------------------------------------------------- #
_PLAN_SYS = (
    "You plan retrieval for a pharma competitive-intelligence agent. Given a QUESTION, produce "
    "`sub_queries`: short search queries whose results will answer it. If the question is a single "
    "fact needing no breakdown, return EXACTLY ONE sub-query (you may restate the question). Do NOT "
    "answer the question — only produce sub-queries."
)

_ASSESS_SYS = (
    "You assess evidence sufficiency for a pharma CI agent. You are given a QUESTION and a NUMBERED "
    "EVIDENCE list. Choose `kind`:\n"
    "- 'sufficient': the evidence answers the question — leave missing_slots / follow_up_sub_queries / "
    "gaps empty.\n"
    "- 'gap': the answer is not yet in the evidence but a lookup would help — set "
    "`follow_up_sub_queries` and `missing_slots` (what is missing), and set `gap_kind` to name the "
    "SOURCE to consult:\n"
    "    * 'corpus' (the default): re-query the document corpus; put the new search queries in "
    "`follow_up_sub_queries`.\n"
    "    * 'trial_status': a clinical-trial / recruitment status, answerable by a clinical-trials "
    "registry lookup.\n"
    "    * 'regulatory_status': a drug approval / regulatory status, answerable by an FDA approval "
    "lookup.\n"
    "  For a 'trial_status' or 'regulatory_status' gap, `follow_up_sub_queries[0]` MUST be the exact "
    "search identifier to look up — the development code or drug name as it appears in the evidence, "
    "not a sentence. Default to 'corpus' when unsure.\n"
    "- 'exhausted': more retrieval will NOT help — set `gaps` (what remains unanswerable).\n"
    "SUBJECT CHECK (be honest — do not over-claim sufficiency): choose 'sufficient' ONLY when the "
    "evidence actually addresses the SPECIFIC subject the question names — its named company, drug, "
    "indication, or fact. Evidence about a neighbouring company, a different drug, or merely the same "
    "disease area does NOT make the question answerable. If the question's specific subject is not "
    "present in the evidence, do NOT return 'sufficient': return 'gap' (with `follow_up_sub_queries`) "
    "if a different retrieval might surface it, or 'exhausted' (naming the absent subject in `gaps`) "
    "if that subject is simply not present in this corpus.\n"
    "You JUDGE ONLY: do not write the answer and do not output any terminal state."
)

_SYNTH_SYS = (
    "You synthesize the answer for a pharma CI agent. You are given a QUESTION and a NUMBERED EVIDENCE "
    "list; each item is prefixed with its integer index in brackets, e.g. [0], [1]. Produce `claims`, "
    "each with `subject`, `attribute`, `value` (short strings) and `citations`: the list of INTEGER "
    "indices of the evidence items that support the claim, e.g. [0, 2]. "
    "WRITE A FULLY-QUALIFIED `attribute`: name precisely what the value is about by carrying the "
    "qualifying context the fact has in the evidence — the indication or disease, the time period or "
    "reporting quarter, the geography/region, and the scope or development stage it refers to. Prefer a "
    "contextual attribute like 'net sales for <the stated period>', 'approval status in <the specific "
    "indication>', or 'development stage for <the condition> in <the region>' over a bare attribute "
    "like 'net sales', 'approval status', or 'stage'. Use ONLY qualifying context that the evidence "
    "itself states — never invent a period, indication, or region that is not present in the evidence. "
    "CITE BY INTEGER INDEX ONLY — "
    "never output a document name, id, or line range; only the bracketed integers shown. Assert only "
    "claims the evidence supports; if nothing is supported, return an empty `claims` list. Do not "
    "invent facts."
)


def _format_contents(question: str, evidence: list[EvidenceItem]) -> str:
    """QUESTION + the 0-based NUMBERED evidence list (text only — no doc_id / line range, §5.7)."""
    listing = "\n".join(f"[{i}] {e.text}" for i, e in enumerate(evidence)) or "(no evidence)"
    return f"QUESTION: {question}\n\nNUMBERED EVIDENCE:\n{listing}"


class GeminiLLMSeam:
    """The real ``types.LLMSeam`` — drives PLAN / ASSESS / SYNTHESIZE via Gemini structured output."""

    def __init__(self, temperature: float = 0.0) -> None:
        self.temperature = temperature

    def plan(self, question: str) -> PlanOutput:
        resp = generate_structured(f"QUESTION: {question}", _PlanResponse,
                                   system_instruction=_PLAN_SYS, temperature=self.temperature)
        subs = [s for s in resp.sub_queries if s.strip()] or [question]  # ≥1 (degenerate = the question)
        return PlanOutput(sub_queries=subs)

    def assess(self, question: str, evidence: list[EvidenceItem]) -> AssessVerdict:
        resp = generate_structured(_format_contents(question, evidence), _AssessResponse,
                                   system_instruction=_ASSESS_SYS, temperature=self.temperature)
        # Per-kind construction -> a well-formed verdict (the loop enforces well-formedness loudly).
        if resp.kind == "sufficient":
            return AssessVerdict(kind="sufficient")
        if resp.kind == "gap":
            return AssessVerdict(kind="gap", gap_kind=resp.gap_kind, missing_slots=resp.missing_slots,
                                 follow_up_sub_queries=resp.follow_up_sub_queries)
        return AssessVerdict(kind="exhausted", gaps=resp.gaps)

    def synthesize(self, question: str, evidence: list[EvidenceItem]) -> SynthesizeOutput:
        resp = generate_structured(_format_contents(question, evidence), _SynthResponse,
                                   system_instruction=_SYNTH_SYS, temperature=self.temperature)
        claims = [Claim(subject=c.subject, attribute=c.attribute, value=c.value, citations=list(c.citations))
                  for c in resp.claims]
        return SynthesizeOutput(claims=claims)
