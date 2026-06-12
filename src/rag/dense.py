"""FAISS dense index: build / persist / load + query.

FAISS stores **vectors only**, so the ``id -> RetrievalUnit`` map (``units.json``) and the
index metadata (``meta.json``: embedding model, dim, count, chunk config) persist alongside
the index — a FAISS hit (a row id) becomes a ``RetrievalUnit`` via that map. The index is a
deterministic function of ``(chunk corpus, pinned EMBED_MODEL)``: built once, loaded per run,
never re-embedded to iterate. Cosine similarity via inner product over L2-normalized vectors.
"""

import json
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from .embeddings import Embedder
from .units import RetrievalUnit

INDEX_FILE = "chunks.faiss"
UNITS_FILE = "units.json"
META_FILE = "meta.json"


def build_and_persist(
    units: list[RetrievalUnit], embedder: Embedder, out_dir: str | Path,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Embed the units, build a cosine (IP over L2-normalized) FAISS index, persist all three files."""
    out_dir = Path(out_dir)
    vecs = embedder.embed_documents([u.text for u in units])
    faiss.normalize_L2(vecs)
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)

    out_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(out_dir / INDEX_FILE))
    (out_dir / UNITS_FILE).write_text(
        json.dumps([u.to_dict() for u in units], ensure_ascii=False), encoding="utf-8"
    )
    meta: dict[str, Any] = {
        "embed_model": embedder.model_name,
        "dim": int(vecs.shape[1]),
        "num_units": len(units),
        "metric": "cosine (inner product over L2-normalized vectors)",
        **(extra_meta or {}),
    }
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


class DenseIndex:
    """A loaded FAISS index + its id->unit map. ``search`` returns (unit_index, score)."""

    def __init__(self, index: Any, units: list[RetrievalUnit], embedder: Embedder, meta: dict[str, Any]) -> None:
        self.index = index
        self.units = units
        self.embedder = embedder
        self.meta = meta

    @classmethod
    def load(cls, out_dir: str | Path, embedder: Embedder) -> "DenseIndex":
        out_dir = Path(out_dir)
        index = faiss.read_index(str(out_dir / INDEX_FILE))
        units = [RetrievalUnit.from_dict(d) for d in json.loads((out_dir / UNITS_FILE).read_text(encoding="utf-8"))]
        meta = json.loads((out_dir / META_FILE).read_text(encoding="utf-8"))
        return cls(index, units, embedder, meta)

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        qv = self.embedder.embed_query(query)
        faiss.normalize_L2(qv)
        scores, ids = self.index.search(qv, top_k)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]
