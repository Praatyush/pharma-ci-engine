"""Production ``types.ToolSeam`` — a thin pass-through to the committed live-tool clients.

The two Phase-4C live tools (``clinicaltrials_lookup`` / ``fda_lookup`` in ``src/tools``) behind the
``types.ToolSeam`` Protocol the loop dispatches to. **No added logic** — each method delegates directly
to the committed client function (which owns the httpx call, timeout, User-Agent, env base URL, and the
optional openFDA key). Injected into ``run_agent`` so dispatch stays code-owned and unit-testable
without the network: tests substitute a stub ``ToolSeam`` exactly as they stub the LLM / retriever
seams.
"""

from src.tools.clinicaltrials import TrialRecord, clinicaltrials_lookup
from src.tools.fda import FdaApprovalRecord, fda_lookup


class LiveToolSeam:
    """The real ``types.ToolSeam`` — delegates verbatim to the committed clients."""

    def clinicaltrials_lookup(self, query: str) -> list[TrialRecord]:
        return clinicaltrials_lookup(query)

    def fda_lookup(self, query: str) -> list[FdaApprovalRecord]:
        return fda_lookup(query)
