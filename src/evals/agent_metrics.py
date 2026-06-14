"""Phase 4A answer-level scorer metrics (Batch 2) — the four metrics of ``docs/AGENT_CONTRACT.md`` §3.

Each function is PURE (inputs -> result, no side effects) and operates on one
``(resolved_answer_object, golden_question)`` pair. ``golden_question`` is one question dict as loaded
from ``src/evals/golden/agent.golden.json`` (keys: ``expected_terminal_state``, ``reference_claims``;
each reference claim has ``subject`` / ``attribute`` / ``value`` / ``acceptable_spans``).

Value comparisons use the deterministic value layer (``agent_value_match.value_match``, Batch-2
ratified). ``(subject, attribute)`` comparisons use ``normalize.token_set_match`` — the established
open-text matcher augmented with a true token-SET ratio so a reorder-plus-function-word attribute
paraphrase is credited; the STRICT ``normalize.fuzzy_match`` is reserved for extraction/indication
matching, where subset-containment must stay a non-match. Citation containment reuses
``retrieval_scorer.line_containment`` (the ONE overlap function) — confirmed at build to accept the
Batch-1 ``Span`` as its unit operand.

§4 (insufficient-expected questions, empty ``reference_claims``): claim metrics are NOT meaningful —
the pass criterion is ``terminal_state == "insufficient_evidence" AND zero claims`` (see
:func:`insufficient_pass`). On those questions recall/precision/faithfulness return ``meaningful=False``
with a ``None`` score (never a misleading 0 or 1).

PRECISION / FAITHFULNESS SCOPE (matched-only — reconciles §3.3 and §3.4). Precision and faithfulness
are computed ONLY over agent claims that MATCH a golden reference claim on normalized (subject,
attribute). A matched claim is SUPPORTED iff all its citations are faithful against THAT matched golden
claim's acceptable_spans (binary containment, OR-semantics). Agent claims matching NO golden reference
claim are EXCLUDED from both denominators — neither credited nor penalized. That is how §3.3's
"don't penalize true-but-unlisted claims" is honored, deterministically (matching is plain (subject,
attribute) keying): e.g. a correct unlisted P1 TAK-360 claim cited to TAK-360's real span is simply
excluded, not marked unfaithful against P1's single TAK-861 span. The count of such claims is surfaced
as a diagnostic ("unlisted claims surfaced"), never folded into precision.

KNOWN LIMITATION (logged). Deterministic precision catches bad citations on golden-KNOWN (subject,
attribute) pairs — a claim matching a golden (subject, attribute) but citing a wrong span IS scored and
FAILS. It does NOT catch a wholly-invented claim about a subject/attribute ABSENT from the golden: there
is no golden claim to match it against, and detecting it needs semantic source-checking, i.e. the
deferred LLM judge. Such claims are out of baseline scope (counted as "unlisted", not scored).
"""

from dataclasses import dataclass
from typing import Any

from src.evals import normalize as N
from src.evals.agent_value_match import value_match
from src.evals.answer_object import ResolvedAnswerObject, ResolvedClaim, Span
from src.evals.retrieval_scorer import line_containment


# --------------------------------------------------------------------------- #
# Result structures
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RecallResult:
    meaningful: bool                 # False on insufficient-expected questions
    n_reference: int
    n_recalled: int
    recall: float | None
    wrong_value: tuple[str, ...]     # reference claim_ids matched on (subject, attribute) but WRONG value


@dataclass(frozen=True)
class PrecisionResult:
    meaningful: bool
    n_claims: int                    # total agent claims emitted
    n_matched: int                   # agent claims matched to a golden (subject, attribute) = precision denominator
    n_supported: int                 # matched claims whose citations are ALL faithful
    n_unlisted: int                  # agent claims matching NO golden reference claim (diagnostic; excluded, not penalized)
    precision: float | None          # n_supported / n_matched; None when no matched claims


@dataclass(frozen=True)
class FaithfulnessResult:
    meaningful: bool
    n_citations: int                 # uncited claims contribute 0 to the denominator (§3.4)
    n_faithful: int
    faithfulness: float | None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _is_insufficient_expected(golden_q: dict[str, Any]) -> bool:
    return not golden_q.get("reference_claims")


def _subj_attr_match(claim: ResolvedClaim, ref: dict[str, Any]) -> bool:
    # Token-SET matcher (NOT the strict extraction `fuzzy_match`): credits a reorder-plus-function-word
    # attribute paraphrase ("net sales for Q1 2026" ~ "Q1 2026 net sales") and an asset-name subset
    # ("Takeda" ~ "Takeda pipeline"). Genuine subject-granularity errors (company "Takeda" vs drug
    # "mezagitamab") share no tokens and still fail; the value layer is recall's second gate.
    return N.token_set_match(claim.subject, ref["subject"]) and N.token_set_match(claim.attribute, ref["attribute"])


def _ref_spans(ref: dict[str, Any]) -> list[Span]:
    # A present [start, end] → tuple (as today); a null/missing line_range → None (a record-identity
    # acceptable span, e.g. a tool claim's ctgov:/openfda: record — degrade safely, never index a null).
    spans: list[Span] = []
    for s in ref["acceptable_spans"]:
        lr = s.get("line_range")
        spans.append(Span(doc_id=s["doc_id"], line_range=(lr[0], lr[1]) if lr is not None else None))
    return spans


def _matched_refs(claim: ResolvedClaim, golden_q: dict[str, Any]) -> list[dict[str, Any]]:
    """Golden reference claims this agent claim matches on normalized (subject, attribute) — the
    precision/faithfulness match key (value is NOT required here; value-correctness is recall's job)."""
    return [ref for ref in golden_q["reference_claims"] if _subj_attr_match(claim, ref)]


def _matched_pool(refs: list[dict[str, Any]]) -> list[Span]:
    """Union of the matched reference claims' acceptable_spans (OR-semantics across them)."""
    pool: list[Span] = []
    for ref in refs:
        pool += _ref_spans(ref)
    return pool


def _span_contained(agent_span: Span, pool: list[Span]) -> bool:
    """Is the agent's cited span faithful against the pool? Matches ONLY same-provenance-form members:

    - **Tool claim** (``agent_span.line_range is None``, a record-identity citation, AGENT_CONTRACT §6.2):
      faithful iff some pool span ALSO has ``line_range is None`` AND the SAME ``doc_id`` — record-identity
      equality (e.g. ``ctgov:<NCT>`` ↔ ``ctgov:<NCT>``), no line-span arithmetic. A None agent span never
      matches a tuple-line_range acceptable span by doc_id coincidence — both sides must be None.
    - **Corpus claim** (``agent_span.line_range`` is a tuple): unchanged — ``acceptable_span ⊆ agent_span``
      (the blessed sub-chunk region falls WITHIN the agent's cited chunk; §3.4, direction corrected by the
      Batch-6a Q1 run). ``line_containment(acc, agent) == 1.0`` ⟺ acc ⊆ agent. Only TUPLE-line_range pool
      members are considered — a None-line_range acceptable span is skipped (never passed into
      ``line_containment``, which unpacks the tuple). No threshold / no fractional credit.

    The two provenance forms are disjoint and never compared; ``line_containment`` is only ever called
    with two tuples.
    """
    if agent_span.line_range is None:   # tool claim → record-identity equality (None ↔ None, same doc_id)
        return any(acc.line_range is None and acc.doc_id == agent_span.doc_id for acc in pool)
    # corpus claim → tuple containment; skip any None-line_range pool member (mixed forms never match).
    return any(acc.line_range is not None and line_containment(acc.doc_id, acc.line_range, agent_span) == 1.0
               for acc in pool)


# --------------------------------------------------------------------------- #
# The four metrics (§3) + the §4 insufficient pass
# --------------------------------------------------------------------------- #
def terminal_state_correct(answer: ResolvedAnswerObject, golden_q: dict[str, Any]) -> bool:
    """§3.1 — exact enum match between the answer's terminal_state and the golden's expected."""
    return answer.terminal_state == golden_q["expected_terminal_state"]


def claim_recall(answer: ResolvedAnswerObject, golden_q: dict[str, Any]) -> RecallResult:
    """§3.2 — fraction of golden reference claims matched by some agent claim (normalized
    (subject, attribute) match AND value-match). Separately reports the WRONG-VALUE diagnostic:
    reference claims matched on (subject, attribute) but with a wrong value (NOT folded into recall)."""
    refs = golden_q.get("reference_claims") or []
    if not refs:
        return RecallResult(meaningful=False, n_reference=0, n_recalled=0, recall=None, wrong_value=())
    recalled = 0
    wrong: list[str] = []
    for ref in refs:
        subj_attr = [a for a in answer.claims if _subj_attr_match(a, ref)]
        if any(value_match(a.value, ref["value"]) for a in subj_attr):
            recalled += 1
        elif subj_attr:
            wrong.append(ref.get("claim_id", "?"))
    return RecallResult(True, len(refs), recalled, recalled / len(refs), tuple(wrong))


def claim_precision(answer: ResolvedAnswerObject, golden_q: dict[str, Any]) -> PrecisionResult:
    """§3.3 (matched-only — see module docstring) — over agent claims that MATCH a golden reference
    claim on normalized (subject, attribute): the fraction whose citations are ALL faithful against that
    matched claim's acceptable_spans. An uncited matched claim is UNSUPPORTED. Agent claims matching no
    reference claim are EXCLUDED (surfaced as ``n_unlisted``), so true-but-unlisted claims aren't
    penalized; a wholly-invented claim about a golden-absent subject is also excluded (LLM-judge
    territory — logged limitation)."""
    if _is_insufficient_expected(golden_q):
        return PrecisionResult(meaningful=False, n_claims=len(answer.claims),
                               n_matched=0, n_supported=0, n_unlisted=0, precision=None)
    n_matched = 0
    n_supported = 0
    n_unlisted = 0
    for a in answer.claims:
        refs = _matched_refs(a, golden_q)
        if not refs:
            n_unlisted += 1
            continue
        n_matched += 1
        if a.citations and all(_span_contained(c, _matched_pool(refs)) for c in a.citations):
            n_supported += 1
    precision = (n_supported / n_matched) if n_matched else None
    return PrecisionResult(True, len(answer.claims), n_matched, n_supported, n_unlisted, precision)


def citation_faithfulness(answer: ResolvedAnswerObject, golden_q: dict[str, Any]) -> FaithfulnessResult:
    """§3.4 (matched-only) — per-citation binary containment (acceptable_span ⊆ agent_span — the blessed
    region falls within the agent's cited chunk; OR over the matched golden claim's spans). Citations on
    agent claims that match no reference claim are excluded from the denominator (not assessable against
    the golden); uncited claims contribute nothing."""
    if _is_insufficient_expected(golden_q):
        return FaithfulnessResult(meaningful=False, n_citations=0, n_faithful=0, faithfulness=None)
    total = 0
    faithful = 0
    for a in answer.claims:
        refs = _matched_refs(a, golden_q)
        if not refs:
            continue
        pool = _matched_pool(refs)
        for c in a.citations:
            total += 1
            if _span_contained(c, pool):
                faithful += 1
    return FaithfulnessResult(True, total, faithful, (faithful / total) if total else None)


def insufficient_pass(answer: ResolvedAnswerObject, golden_q: dict[str, Any]) -> bool:
    """§4 — the pass criterion for an insufficient-expected question: terminal_state is
    ``insufficient_evidence`` AND the agent emitted ZERO claims. (Caller applies this only when
    ``golden_q`` is insufficient-expected; on those questions terminal-state correctness is the
    load-bearing signal and precision/faithfulness are non-meaningful.)"""
    return answer.terminal_state == "insufficient_evidence" and len(answer.claims) == 0
