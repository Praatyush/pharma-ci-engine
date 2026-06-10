"""Isolated Gemini access — the ONLY module that imports ``google.genai``.

Reads the API key + model name from the environment, wraps a single
structured-output call, and hand-rolls retry/backoff (stdlib; not tenacity, even
though it is now transitively installed). Transient errors are retried with
*separate* backoff schedules:

- ``429`` (rate/quota — our limit): longer backoff.
- ``503`` (capacity blip on Google's side): shorter backoff.

All other errors — including ``400`` schema rejections — propagate immediately.
"""

import os
import random
import time
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

_T = TypeVar("_T", bound=BaseModel)

# code -> (max_attempts, base_delay_seconds). 429 backs off longer than 503.
_BACKOFF: dict[int, tuple[int, float]] = {
    429: (5, 4.0),
    503: (4, 1.0),
}

_client: genai.Client | None = None


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Add it to .env, then: set -a; source .env; set +a"
        )
    return value


def get_client() -> genai.Client:
    """Lazily build (and cache) a Gemini client from ``GEMINI_API_KEY``."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=_require_env("GEMINI_API_KEY"))
    return _client


def _backoff_for(code: int | None) -> tuple[int, float] | None:
    """Retry budget for a transient HTTP status, or None if it must propagate."""
    return _BACKOFF.get(code) if code is not None else None


def generate_structured(
    contents: str,
    response_schema: type[_T],
    *,
    system_instruction: str,
    temperature: float = 0.0,
) -> _T:
    """One structured-output call; returns the parsed Pydantic instance.

    Retries 429 (long backoff) and 503 (short backoff); every other error —
    including a 400 schema rejection — propagates immediately. A response that
    fails to parse into ``response_schema`` is surfaced, never silently parsed
    from free text.
    """
    client = get_client()
    model = _require_env("GEMINI_MODEL")
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=temperature,
    )

    max_attempts = max(attempts for attempts, _ in _BACKOFF.values())
    for attempt in range(max_attempts):
        try:
            response = client.models.generate_content(
                model=model, contents=contents, config=config
            )
            parsed = response.parsed
            if not isinstance(parsed, response_schema):
                raise RuntimeError(
                    f"Gemini returned no parseable {response_schema.__name__} "
                    f"(got {type(parsed).__name__})."
                )
            return parsed
        except errors.APIError as exc:
            budget = _backoff_for(getattr(exc, "code", None))
            if budget is None or attempt >= budget[0] - 1:
                raise
            base = budget[1]
            time.sleep(base * (2 ** attempt) + random.uniform(0, base / 2))

    raise RuntimeError("retry loop exhausted without returning")  # unreachable
