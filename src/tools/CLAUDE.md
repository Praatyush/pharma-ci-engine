# CLAUDE.md — `src/tools`

## Purpose

External API clients that keep the system current instead of limited to static
PDFs:

- **ClinicalTrials.gov** (v2 API) — trial status, phase, endpoints.
- **FDA / EMA** (openFDA) — approvals, regulatory actions.

Consumed by `src/agent` as `clinicaltrials_lookup` and `fda_lookup`.

## Run & test

```bash
pytest tests/tools -q              # client tests, mocked HTTP (added in Phase 4)
```

## Conventions

- Use `httpx` with explicit timeouts; set a descriptive User-Agent (FDA
  etiquette). API base URLs come from env (`.env.example`), not hardcoded.
- Map raw API JSON into typed results (Pydantic) so the agent + evals consume a
  stable contract, not vendor payloads.
- Mock HTTP in tests — no live network calls in the test suite.
- Respect rate limits; openFDA key is optional but raises limits when set.

## Gotchas

_None yet._
