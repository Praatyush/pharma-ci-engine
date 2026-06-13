"""openFDA Drugs@FDA client — ``fda_lookup``.

Queries the openFDA Drugs@FDA endpoint (``/drug/drugsfda.json``) by drug name —
brand or generic — and maps each matching application into a typed
:class:`FdaApprovalRecord`. Per ``src/tools/CLAUDE.md``: ``httpx`` with an explicit
timeout, a descriptive User-Agent, the base URL read from env (``FDA_API_BASE``,
with the documented public default), the optional ``OPENFDA_API_KEY`` appended only
when present (it raises rate limits; its **absence is NOT an error** — proceed
keyless, AGENT_PLAN §9.3), and a typed Pydantic result so the agent + evals consume
a stable contract, not the raw openFDA payload.

Scope (Phase 4C, second client): a plain client that parses a *successful*
response, mirroring ``clinicaltrials.py``. Retry/backoff, the
tool-failure-to-typed-result mapping (AGENT_PLAN §9.3), and recorded HTTP fixtures
(AGENT_CONTRACT §6.5) are deliberately later steps — not here. HTTP errors
propagate (the project's let-it-raise convention); nothing in this module touches
the network at import time.
"""

import os

import httpx
from pydantic import BaseModel

# Public openFDA base, configurable via env (``FDA_API_BASE`` — the var already in
# .env.example, reused rather than minting a second name). Mirrors the rag
# ``EMBED_MODEL`` default-bearing/no-key pattern, not the ``_require_env`` paid-API
# one — the URL is read from env, never a magic constant in the request call.
DEFAULT_OPENFDA_API_BASE = "https://api.fda.gov"

# Descriptive User-Agent per the CLAUDE.md FDA-etiquette convention.
_USER_AGENT = "pharma-ci-engine/0.1 (openFDA Drugs@FDA client)"

# Explicit request timeout (seconds) — never rely on httpx's implicit default.
_TIMEOUT_SECONDS = 15.0

# openFDA returns a SINGLE record when no limit is set, so an explicit limit is
# REQUIRED to retrieve the match set. Caps a single-request lookup (no pagination).
_LIMIT = 20


class FdaApprovalRecord(BaseModel):
    """One Drugs@FDA application, reduced to the four fields the agent needs.

    ``submission_status`` is the **original submission's** FDA approval-status code
    (e.g. ``"AP"`` = approved) — **the approval signal**, captured verbatim as a
    plain ``str`` for source-vocabulary resilience; turning that controlled
    vocabulary into a matchable atom is the value-layer's job (AGENT_CONTRACT §6.4,
    where openFDA "approved" reuses the existing status atom), not the client's.
    ``marketing_status`` was deliberately **NOT** used — it is per-*product*
    marketing disposition (e.g. "Prescription" / "Discontinued"), not the
    application's approval status. ``brand_name`` / ``generic_name`` take the first
    ``openfda`` list entry; every field degrades to ``""`` on an unexpected
    response shape rather than raising.
    """

    application_number: str
    brand_name: str
    generic_name: str
    submission_status: str


def _base_url() -> str:
    """``FDA_API_BASE`` from env, else the documented public openFDA default."""
    base = os.environ.get("FDA_API_BASE") or DEFAULT_OPENFDA_API_BASE
    return base.rstrip("/")


def _first_str(values: object) -> str:
    """First element of an openFDA list field as a string, else ``""``."""
    if isinstance(values, list) and values:
        return str(values[0])
    return ""


def _original_submission_status(submissions: object) -> str:
    """Approval-status code of the ORIG submission, else ``""`` (no clear original).

    openFDA marks each submission ``submission_type`` ``"ORIG"`` (the original
    application) or ``"SUPPL"`` (a supplement). The approval signal lives on the
    original; if no ORIG submission is present we degrade to ``""`` rather than
    raise.
    """
    if not isinstance(submissions, list):
        return ""
    for submission in submissions:
        if isinstance(submission, dict) and submission.get("submission_type") == "ORIG":
            return str(submission.get("submission_status") or "")
    return ""


def _to_record(result: dict) -> FdaApprovalRecord:
    """Map one Drugs@FDA application into a :class:`FdaApprovalRecord`."""
    openfda = result.get("openfda", {})
    if not isinstance(openfda, dict):
        openfda = {}
    return FdaApprovalRecord(
        application_number=str(result.get("application_number", "") or ""),
        brand_name=_first_str(openfda.get("brand_name")),
        generic_name=_first_str(openfda.get("generic_name")),
        submission_status=_original_submission_status(result.get("submissions")),
    )


def fda_lookup(query: str) -> list[FdaApprovalRecord]:
    """Return the Drugs@FDA applications matching a drug name (brand or generic).

    Issues a single GET to the openFDA ``/drug/drugsfda.json`` endpoint, searching
    the term against both ``openfda.brand_name`` and ``openfda.generic_name``, and
    returns the matching applications — no filtering, no summary/grouping. An
    explicit ``limit`` is required (openFDA returns one record otherwise) and there
    is no pagination. The optional ``OPENFDA_API_KEY`` is appended only when set
    (absence is fine — keyless). Each application maps to a
    :class:`FdaApprovalRecord`. Parses a successful response only; HTTP errors
    propagate (the typed-failed-result handling is a later step, AGENT_PLAN §9.3).
    """
    url = f"{_base_url()}/drug/drugsfda.json"
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    search = f'openfda.brand_name:"{query}" OR openfda.generic_name:"{query}"'
    params: dict[str, str | int] = {
        "search": search,
        "limit": _LIMIT,
    }
    api_key = os.environ.get("OPENFDA_API_KEY")
    if api_key:
        params["api_key"] = api_key

    with httpx.Client(timeout=_TIMEOUT_SECONDS, headers=headers) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        body = response.json()

    return [_to_record(result) for result in body.get("results", [])]
