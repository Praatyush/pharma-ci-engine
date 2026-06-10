"""Tests for src/extraction/gemini_client.py — retry/backoff + env handling.

No real client is built and no network call is made: the client is faked and
``time.sleep`` is stubbed.
"""

import pytest
from google.genai import errors

from src.extraction import gemini_client
from src.extraction.models import ChunkExtraction


class _FakeAPIError(errors.APIError):
    """An APIError with a controllable .code, bypassing the real __init__."""

    def __init__(self, code: int):
        self.code = code
        self.message = f"fake {code}"


class _FakeResponse:
    def __init__(self, parsed):
        self.parsed = parsed


class _FakeModels:
    def __init__(self, behaviors):
        self.behaviors = list(behaviors)
        self.calls = 0

    def generate_content(self, *, model, contents, config):
        behavior = self.behaviors[self.calls]
        self.calls += 1
        if isinstance(behavior, Exception):
            raise behavior
        return behavior


class _FakeClient:
    def __init__(self, behaviors):
        self.models = _FakeModels(behaviors)


@pytest.fixture(autouse=True)
def _fast_sleep_and_model(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    monkeypatch.setattr(gemini_client.time, "sleep", lambda _s: None)


def _patch_client(monkeypatch, behaviors) -> _FakeClient:
    client = _FakeClient(behaviors)
    monkeypatch.setattr(gemini_client, "get_client", lambda: client)
    return client


def test_backoff_classification():
    assert gemini_client._backoff_for(429) == (5, 4.0)  # rate limit -> longer
    assert gemini_client._backoff_for(503) == (4, 1.0)  # capacity -> shorter
    assert gemini_client._backoff_for(400) is None       # non-transient
    assert gemini_client._backoff_for(None) is None


def test_require_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        gemini_client._require_env("GEMINI_API_KEY")


def test_success_first_try(monkeypatch):
    parsed = ChunkExtraction()
    client = _patch_client(monkeypatch, [_FakeResponse(parsed)])
    out = gemini_client.generate_structured("x", ChunkExtraction, system_instruction="s")
    assert out is parsed
    assert client.models.calls == 1


def test_retries_503_then_succeeds(monkeypatch):
    parsed = ChunkExtraction()
    client = _patch_client(
        monkeypatch, [_FakeAPIError(503), _FakeAPIError(503), _FakeResponse(parsed)]
    )
    out = gemini_client.generate_structured("x", ChunkExtraction, system_instruction="s")
    assert out is parsed
    assert client.models.calls == 3


def test_retries_429_then_succeeds(monkeypatch):
    parsed = ChunkExtraction()
    client = _patch_client(monkeypatch, [_FakeAPIError(429), _FakeResponse(parsed)])
    out = gemini_client.generate_structured("x", ChunkExtraction, system_instruction="s")
    assert out is parsed
    assert client.models.calls == 2


def test_non_transient_400_reraises_immediately(monkeypatch):
    client = _patch_client(monkeypatch, [_FakeAPIError(400)])
    with pytest.raises(errors.APIError):
        gemini_client.generate_structured("x", ChunkExtraction, system_instruction="s")
    assert client.models.calls == 1  # no retry


def test_429_exhausts_budget_then_raises(monkeypatch):
    client = _patch_client(monkeypatch, [_FakeAPIError(429)] * 5)
    with pytest.raises(errors.APIError):
        gemini_client.generate_structured("x", ChunkExtraction, system_instruction="s")
    assert client.models.calls == 5  # 429 budget = 5 attempts


def test_503_exhausts_shorter_budget_then_raises(monkeypatch):
    client = _patch_client(monkeypatch, [_FakeAPIError(503)] * 4)
    with pytest.raises(errors.APIError):
        gemini_client.generate_structured("x", ChunkExtraction, system_instruction="s")
    assert client.models.calls == 4  # 503 budget = 4 attempts


def test_unparseable_response_surfaces(monkeypatch):
    # parsed is None (model returned non-conforming JSON) -> raise, never free-text parse
    _patch_client(monkeypatch, [_FakeResponse(None)])
    with pytest.raises(RuntimeError):
        gemini_client.generate_structured("x", ChunkExtraction, system_instruction="s")
