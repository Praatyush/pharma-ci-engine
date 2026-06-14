"""ClinicalTrials.gov client tests — drive the REAL client request+parse path via an injected
``httpx.MockTransport`` (the AGENT_CONTRACT §6.5 seam); no network, keyless. MockTransport is a new
pattern for this repo's suite. Fixtures load by repo-root-relative path (pytest cwd = repo root).
"""

import json

import httpx
import pytest

from src.tools.clinicaltrials import _USER_AGENT, TrialRecord, clinicaltrials_lookup

FIXTURE = "src/evals/fixtures/clinicaltrials_tak861.json"


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_happy_path_parses_fixture():
    body = _load(FIXTURE)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=body)

    records = clinicaltrials_lookup("TAK-861", transport=httpx.MockTransport(handler))

    # request shape
    req = seen[0]
    assert req.url.path.endswith("/studies")
    assert req.url.params["query.intr"] == "TAK-861"
    assert req.url.params["pageSize"] == "20"
    assert req.url.params["format"] == "json"
    assert req.headers["user-agent"] == _USER_AGENT

    # parsed output (Step-B-validated real values)
    assert len(records) == 6
    assert all(isinstance(r, TrialRecord) for r in records)
    by_id = {r.nct_id: r for r in records}
    assert by_id["NCT06470828"].status == "COMPLETED"
    assert by_id["NCT06470828"].phase == "PHASE3"
    assert by_id["NCT05816382"].phase == "PHASE2, PHASE3"   # multi-phase join


def test_timeout_propagates():
    def handler(request):
        raise httpx.TimeoutException("simulated timeout")

    with pytest.raises(httpx.TimeoutException):
        clinicaltrials_lookup("x", transport=httpx.MockTransport(handler))


def test_http_error_status_raises():
    def handler(request):
        return httpx.Response(500)

    with pytest.raises(httpx.HTTPStatusError):       # via the client's raise_for_status()
        clinicaltrials_lookup("x", transport=httpx.MockTransport(handler))


def test_malformed_body_raises():
    def handler(request):
        return httpx.Response(200, content=b"not json")

    with pytest.raises(json.JSONDecodeError):        # the client's response.json() parse
        clinicaltrials_lookup("x", transport=httpx.MockTransport(handler))
