"""The retrieval unit — the leg-agnostic thing both legs emit and the scorer consumes.

A ``RetrievalUnit`` carries ``(doc_id, line_range)`` — the key the shared scorer
(``src/evals/retrieval_scorer.py``) overlap-tests against the golden's span keys — plus
the unit ``text`` and a ``kind``/``payload`` for provenance. For Stage A2a only chunk
units exist (``kind="chunk"``, ``line_range`` straight from the ingestion ``Chunk``);
Stage B will emit entity units (``kind="fact"``) of the same shape, which is what lets
the scorer score either leg unchanged.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievalUnit:
    doc_id: str
    line_range: tuple[int, int]  # 1-based inclusive; the scorer's overlap key
    text: str
    kind: str = "chunk"
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "line_range": [self.line_range[0], self.line_range[1]],
            "text": self.text,
            "kind": self.kind,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RetrievalUnit":
        lr = d["line_range"]
        return cls(d["doc_id"], (lr[0], lr[1]), d["text"], d.get("kind", "chunk"), d.get("payload", {}))
