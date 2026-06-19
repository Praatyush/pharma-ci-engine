"""ClinicalTrials.gov v2 client — ``clinicaltrials_lookup``.

Queries the ClinicalTrials.gov v2 search API by intervention/drug term and maps
each matching study into a typed :class:`TrialRecord`. Per ``src/tools/CLAUDE.md``:
``httpx`` with an explicit timeout, a descriptive User-Agent, the base URL read
from env (``CLINICALTRIALS_API_BASE``, with the documented public default), and a
typed Pydantic result so the agent + evals consume a stable contract — not the raw
v2 payload.

Scope (Phase 4C, first client): a plain client that parses a *successful*
response. Retry/backoff, the tool-failure-to-typed-result mapping (AGENT_PLAN
§9.3), and recorded HTTP fixtures (AGENT_CONTRACT §6.5) are deliberately later
steps — not here. HTTP errors propagate (the project's let-it-raise convention);
nothing in this module touches the network at import time.
"""

import os

import httpx
from pydantic import BaseModel

# Public v2 base, configurable via env. Mirrors the rag ``EMBED_MODEL`` pattern (a
# sensible, reproducible default that needs no key/quota) rather than the
# ``_require_env`` paid-API pattern — the URL is read from env, never a magic
# constant buried in the request call.
DEFAULT_CLINICALTRIALS_API_BASE = "https://clinicaltrials.gov/api/v2"

# Descriptive User-Agent per the CLAUDE.md FDA-etiquette convention.
_USER_AGENT = "pharma-ci-engine/0.1 (ClinicalTrials.gov v2 client)"

# Explicit request timeout (seconds) — never rely on httpx's implicit default.
_TIMEOUT_SECONDS = 15.0

# Caps a single-page lookup — enough to contain the matching trials plus context
# for the agent, not a catalog (v2 allows up to 1000; we do not paginate).
_PAGE_SIZE = 20


class TrialRecord(BaseModel):
    """One ClinicalTrials.gov study, reduced to the four fields the agent needs.

    ``status`` (CT.gov ``overallStatus``) and ``phase`` are captured as plain
    ``str`` **deliberately** — NOT coerced to enums. The client stays resilient to
    source-vocabulary drift (CT.gov can add or rename status/phase values);
    turning a controlled vocabulary into a matchable atom is the value-layer's job
    (AGENT_CONTRACT §6.4), not the client's. ``phase`` joins CT.gov's ``phases``
    list verbatim (multiple phases -> comma-joined; none -> empty string).
    """

    nct_id: str
    title: str
    status: str
    phase: str


def _base_url() -> str:
    """``CLINICALTRIALS_API_BASE`` from env, else the documented public default."""
    base = os.environ.get("CLINICALTRIALS_API_BASE") or DEFAULT_CLINICALTRIALS_API_BASE
    return base.rstrip("/")


def _to_record(study: dict) -> TrialRecord:
    """Map one v2 study object into a :class:`TrialRecord` (the four fields only)."""
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    phases = design.get("phases") or []
    return TrialRecord(
        nct_id=identification.get("nctId", ""),
        title=identification.get("briefTitle", ""),
        status=status.get("overallStatus", ""),
        phase=", ".join(phases),
    )


def clinicaltrials_lookup(query: str, transport: httpx.BaseTransport | None = None) -> list[TrialRecord]:
    """Return the ClinicalTrials.gov studies matching an intervention/drug term.

    Issues a single GET to the v2 ``/studies`` endpoint by intervention query
    (``query.intr``) and returns the matching trials from that one page — no
    pagination, no filtering, no status selection, no summary/grouping. Each study
    maps to a :class:`TrialRecord`. Parses a successful response only; HTTP errors
    propagate (the typed-failed-result handling is a later step, AGENT_PLAN §9.3).

    ``transport`` is the AGENT_CONTRACT §6.5 injected-transport seam: default ``None``
    uses httpx's real network transport (every live caller is unchanged); tests / the
    fixture-backed eval inject a ``MockTransport`` so the same request+parse path runs
    keyless and networkless.
    """
    url = f"{_base_url()}/studies"
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    params: dict[str, str | int] = {
        "query.intr": query,
        "pageSize": _PAGE_SIZE,
        "format": "json",
    }

    with httpx.Client(timeout=_TIMEOUT_SECONDS, headers=headers, transport=transport) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        body = response.json()

    return [_to_record(study) for study in body.get("studies", [])]
