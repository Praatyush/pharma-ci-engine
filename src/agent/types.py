"""Typed shapes + stubbable seams for the Phase 4A research-agent control loop (Batch 4).

The structured I/O of the three LLM calls (AGENT_PLAN §5.4 — PLAN / ASSESS / SYNTHESIZE), the
evidence unit, the trajectory record (§2.5), and the seam ``Protocol``s the loop depends on. This
batch STUBS the LLM + retriever behind these seams (NO real Gemini calls, NO retriever wiring); the
loop control flow + state machine are the deliverable. Batch 5 wires ``corpus_retrieve``; Batch 6
fills the LLM seam with prompts + real model calls.

The answer-object the loop emits is the frozen ``src/evals/answer_object.AnswerObject`` (§1): it
carries ``question_id`` / ``terminal_state`` / ``claims`` only. Receipts (AGENT_PLAN §2.4 "evidence
summary on non-answered states", §5.5 "trajectory receipts") live in the separate :class:`Trajectory`
(§2.5: the answer-object is *what the agent asserts*; the trajectory is *what it did*).
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.evals.answer_object import AnswerObject, Claim

TerminalState = Literal["answered", "partially_answered", "insufficient_evidence"]


# --------------------------------------------------------------------------- #
# LLM-call output schemas (structured outputs; validated)
# --------------------------------------------------------------------------- #
class PlanOutput(BaseModel):
    """PLAN (§5.4): question -> sub-query list. A single-element list is the degenerate
    no-decomposition case, NOT a separate path."""

    model_config = ConfigDict(extra="forbid")
    sub_queries: list[str] = Field(..., min_length=1)


class AssessVerdict(BaseModel):
    """ASSESS (§5.4): judges the evidence so far. Exactly one ``kind``. Judges only — it never
    writes the answer and carries NO terminal_state (the state machine assigns that, §5.5)."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["sufficient", "gap", "exhausted"]
    missing_slots: list[str] = Field(default_factory=list)          # gap: named missing slots
    follow_up_sub_queries: list[str] = Field(default_factory=list)  # gap: queries for the next iteration
    gaps: list[str] = Field(default_factory=list)                   # exhausted: named residual gaps


class SynthesizeOutput(BaseModel):
    """SYNTHESIZE (§5.4/§5.7): final evidence -> claims (citing by evidence INDEX). An empty claim
    list is VALID output (§5.8) and routes to insufficient_evidence."""

    model_config = ConfigDict(extra="forbid")
    claims: list[Claim] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Evidence unit — what the retriever returns; claims cite by index into the accumulated list
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EvidenceItem:
    text: str
    doc_id: str
    line_range: tuple[int, int]


# --------------------------------------------------------------------------- #
# Seams (Protocols) — stubbed in tests; real impls land in Batch 5 (retriever) / Batch 6 (LLM)
# --------------------------------------------------------------------------- #
class LLMSeam(Protocol):
    def plan(self, question: str) -> PlanOutput: ...
    def assess(self, question: str, evidence: list[EvidenceItem]) -> AssessVerdict: ...
    def synthesize(self, question: str, evidence: list[EvidenceItem]) -> SynthesizeOutput: ...


class RetrieverSeam(Protocol):
    # One call per iteration; the real impl (Batch 5) fans out to corpus_retrieve per sub-query
    # and unions by span. corpus_retrieve costs zero LLM requests (§5.1), so fan-out is free.
    def retrieve(self, sub_queries: list[str]) -> list[EvidenceItem]: ...


# --------------------------------------------------------------------------- #
# Trajectory record (§2.5) — what the loop did. Schema'd; the trajectory SCORER is deferred.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IterationRecord:
    index: int
    sub_queries: tuple[str, ...]
    retrieved: tuple[EvidenceItem, ...]
    verdict: AssessVerdict


@dataclass(frozen=True)
class SynthesisValidation:
    attempt: int            # 1 = initial, 2 = the one repair retry (§5.8)
    n_valid: int
    n_dropped: int
    dropped: tuple[str, ...]  # per-dropped-claim error summaries


@dataclass(frozen=True)
class Trajectory:
    question: str
    plan: PlanOutput
    iterations: tuple[IterationRecord, ...]
    synthesis: tuple[SynthesisValidation, ...]
    evidence: tuple[EvidenceItem, ...]   # accumulated — the evidence table a later resolve_citations maps
    terminal_state: TerminalState
    transition_reason: str
    max_iterations: int
    iterations_used: int
    budget_hit: bool


@dataclass(frozen=True)
class AgentRunResult:
    answer: AnswerObject       # what the agent asserts (frozen §1 schema)
    trajectory: Trajectory     # what it did (§2.5)
