"""openFDA Drugs@FDA client tests — drive the REAL client request+parse path via an injected
``httpx.MockTransport`` (the AGENT_CONTRACT §6.5 seam); no network, keyless. MockTransport is a new
pattern for this repo's suite. Fixtures load by repo-root-relative path (pytest cwd = repo root).
"""

import json

import httpx
import pytest

from src.tools.fda import FdaApprovalRecord, fda_lookup

FIXTURE = "src/evals/fixtures/openfda_pitolisant.json"


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_happy_path_parses_fixture(monkeypatch):
    monkeypatch.delenv("OPENFDA_API_KEY", raising=False)   # keyless default
    body = _load(FIXTURE)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=body)

    records = fda_lookup("pitolisant", transport=httpx.MockTransport(handler))

    # request shape
    req = seen[0]
    assert req.url.path.endswith("/drug/drugsfda.json")
    search = req.url.params["search"]
    assert "openfda.brand_name" in search and "openfda.generic_name" in search
    assert req.url.params["limit"] == "20"
    assert "api_key" not in req.url.params

    # parsed output (Step-B-validated real values)
    assert len(records) == 1
    r = records[0]
    assert isinstance(r, FdaApprovalRecord)
    assert r.application_number == "NDA211150"
    assert r.brand_name == "WAKIX"
    assert r.generic_name == "PITOLISANT HYDROCHLORIDE"
    assert r.submission_status == "AP"


def test_api_key_appended_when_set(monkeypatch):
    monkeypatch.setenv("OPENFDA_API_KEY", "testkey")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"results": []})

    fda_lookup("pitolisant", transport=httpx.MockTransport(handler))
    assert seen[0].url.params["api_key"] == "testkey"     # appended when set


def test_no_api_key_when_unset(monkeypatch):
    monkeypatch.delenv("OPENFDA_API_KEY", raising=False)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"results": []})

    fda_lookup("pitolisant", transport=httpx.MockTransport(handler))
    assert "api_key" not in seen[0].url.params            # keyless-default guarantee (absence non-fatal)


def test_timeout_propagates():
    def handler(request):
        raise httpx.TimeoutException("simulated timeout")

    with pytest.raises(httpx.TimeoutException):
        fda_lookup("x", transport=httpx.MockTransport(handler))


def test_http_error_status_raises():
    # openFDA's real no-match is a 404-with-error-body (confirmed); this asserts ONLY the client's
    # CURRENT raise behavior (raise_for_status), NOT §9.3 typed-failed-result wrapper semantics.
    def handler(request):
        return httpx.Response(500)

    with pytest.raises(httpx.HTTPStatusError):
        fda_lookup("x", transport=httpx.MockTransport(handler))
