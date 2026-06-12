"""BM25 keyword leg (``rank-bm25``). The reason BM25 is in the hybrid: drug codes and
endpoint acronyms are exact tokens dense retrieval blurs (TAK-861, VAYHIA, Lp(a)).

Tokenization therefore **preserves** the alphanumerics/hyphens/slashes/parens that carry
that signal — lowercase only, never strip them — so ``TAK-861`` survives as a single token
instead of fragmenting into ``tak`` + ``861``. Built in-memory at load (~134 chunks); cheap,
deterministic, no persistence needed.
"""

import re

from rank_bm25 import BM25Okapi

from .units import RetrievalUnit

# Start on an alphanumeric, then keep internal hyphens/slashes/parens: "tak-861", "p-iii",
# "1/2", "lp(a)" stay whole. (Leading punctuation like "(" is dropped; the drug-code/acronym
# signal — which starts alphanumeric — is preserved.)
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-/()]*")


def tokenize(text: str) -> list[str]:
    """Lowercase + signal-preserving tokenization (keeps drug codes/acronyms intact)."""
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """BM25 over a unit corpus; ``rank`` returns all units best-first as (unit_index, score)."""

    def __init__(self, units: list[RetrievalUnit]) -> None:
        self.units = list(units)
        self._bm25 = BM25Okapi([tokenize(u.text) for u in self.units])

    def rank(self, query: str) -> list[tuple[int, float]]:
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [(i, float(scores[i])) for i in order]
