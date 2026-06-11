"""Isolated embeddings — the ONLY module that imports ``fastembed`` (the isolation lock,
mirroring ``extraction/gemini_client.py`` being the sole ``google.genai`` importer).

Local ONNX inference: **no API key, no quota**, query embedding in-process. The model name
is configurable via ``EMBED_MODEL`` (the ``gemini_client`` env pattern), but — unlike
``GEMINI_MODEL``, which is *required* because there is no sensible default for a paid API —
``EMBED_MODEL`` has a pinned local default so the index is reproducible out of the box. The
index records which model built it (re-embed on model change); see ``dense.py``.
"""

import os

import numpy as np
from fastembed import TextEmbedding

# Pinned local default (small, fast, CPU/ONNX, widely used for retrieval). Configurable.
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


def embed_model_name() -> str:
    """``EMBED_MODEL`` from env, else the pinned local default (no key/quota needed)."""
    return os.environ.get("EMBED_MODEL") or DEFAULT_EMBED_MODEL


class Embedder:
    """Thin wrapper over a fastembed model. Documents and queries embed separately so a
    model with a retrieval query-prefix (e.g. bge) uses it; falls back to plain embed."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or embed_model_name()
        self._model = TextEmbedding(self.model_name)
        self._dim: int | None = None

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.asarray(list(self._model.embed(list(texts))), dtype="float32")

    def embed_query(self, query: str) -> np.ndarray:
        query_embed = getattr(self._model, "query_embed", None)
        if query_embed is not None:
            return np.asarray(list(query_embed([query])), dtype="float32")
        return self.embed_documents([query])

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = int(self.embed_documents(["_probe_"]).shape[1])
        return self._dim
