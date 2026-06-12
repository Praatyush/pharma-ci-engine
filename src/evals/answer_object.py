"""Phase 4A answer-object schema — the research agent's output, typed.

The agent emits an :class:`AnswerObject`; the eval scorer consumes the
:class:`ResolvedAnswerObject` (citations resolved from evidence indices to
``(doc_id, line_range)`` spans by a deterministic code step BEFORE scoring). This is
the typed form of the **frozen** interface in ``docs/AGENT_CONTRACT.md`` §1–§2 — build
against that contract; do not add fields or design here.

Conventions reused from the rest of ``src/evals`` (see ``labels.py``):

- Pydantic v2, a ``_Base`` with ``extra="forbid"`` that every model inherits, so a stray
  or misspelled key fails validation.
- ``line_range`` is ``tuple[int, int]`` (1-based inclusive) — the repo-wide span
  representation (``grounding``/``metrics``/``labels``/``retrieval_scorer``); the same shape
  ``retrieval_scorer.Unit`` carries and ``retrieval_scorer.line_containment`` overlap-tests.

Note (scorer rule, not a schema constraint): AGENT_CONTRACT §4 requires ``claims`` to be
empty on an ``insufficient_evidence`` answer, but that is enforced by the **scorer** — the
schema deliberately ALLOWS an insufficient answer to carry claims so the scorer can catch
that failure mode (a claim emitted on an insufficient question). No cross-field validator here.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The three frozen terminal states (AGENT_CONTRACT §1) — exact spelling/casing of the
# golden's ``expected_terminal_state``.
TerminalState = Literal["answered", "partially_answered", "insufficient_evidence"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ClaimCore(_Base):
    """The three-slot open-string claim key shared by Claim and ResolvedClaim
    (AGENT_CONTRACT §1/§3). subject/attribute/value are OPEN strings — never enums."""

    subject: str = Field(..., description="Open vocabulary — never an enum.")
    attribute: str = Field(..., description="Open vocabulary — never an enum.")
    value: str = Field(..., description="Open vocabulary — never an enum.")


class Claim(_ClaimCore):
    """A claim the agent emits (AGENT_CONTRACT §1).

    ``citations`` are evidence INDICES (ints) into the numbered evidence list the agent was
    shown — never spans. The agent never sees or emits doc_ids / line ranges (§5.7 provenance:
    the model structurally cannot fabricate a span, only reference an integer index).
    """

    citations: list[int] = Field(..., description="Evidence indices into the numbered evidence list (NOT doc_ids / line ranges).")


class Span(_Base):
    """A resolved citation span (AGENT_CONTRACT §2): ``(doc_id, line_range)``.

    ``line_range`` is 1-based inclusive — the repo-wide representation (identical shape to
    ``retrieval_scorer.Unit``; overlap-tested by ``retrieval_scorer.line_containment``).
    """

    doc_id: str = Field(..., description="Document id (full document_id form, as used in the goldens).")
    line_range: tuple[int, int] = Field(..., description="1-based inclusive (start, end).")


class ResolvedClaim(_ClaimCore):
    """A claim after citation resolution (AGENT_CONTRACT §2): identical to :class:`Claim`
    except ``citations`` are resolved from evidence indices to :class:`Span` objects."""

    citations: list[Span] = Field(..., description="Resolved spans (from evidence indices via the deterministic resolve_citations step).")


class _AnswerCore(_Base):
    """Fields shared by AnswerObject and ResolvedAnswerObject."""

    question_id: str = Field(..., description="Matches a golden question_id.")
    terminal_state: TerminalState = Field(..., description='Exactly "answered" | "partially_answered" | "insufficient_evidence".')


class AnswerObject(_AnswerCore):
    """What the research agent emits (AGENT_CONTRACT §1).

    ``claims`` is a list and MAY be empty (the insufficient_evidence case).
    """

    claims: list[Claim] = Field(..., description="List of Claim; may be empty for an insufficient_evidence answer.")


class ResolvedAnswerObject(_AnswerCore):
    """The form the scorer consumes (AGENT_CONTRACT §2): an :class:`AnswerObject` whose
    claims' citations have been resolved to :class:`Span`s by ``resolve_citations`` before
    scoring. ``claims`` MAY be empty (the insufficient_evidence case)."""

    claims: list[ResolvedClaim] = Field(..., description="List of ResolvedClaim; may be empty for an insufficient_evidence answer.")
