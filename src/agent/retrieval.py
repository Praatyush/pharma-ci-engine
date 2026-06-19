"""corpus_retrieve — the agent's §5.3 corpus tool, wrapping the COMMITTED Phase 3 retriever.

``corpus_retrieve(query)`` returns the span-keyed union of the chunk leg's top-10 and the fused
(chunk ∪ entity, span-keyed RRF) top-10 — **≤20 spans**, deduped on ``(doc_id, line_range)``, each
carrying its **chunk text** + ``(doc_id, line_range)``. ``k = 10`` is FIXED, not agent-controllable
(§5.3). It wires to the committed Phase 3 code (``src.rag.chunk_leg`` / ``src.rag.entity_leg`` /
``src.rag.fusion.rrf_fuse_by_span``) — no retrieval is reimplemented here.

The union operationalizes the fusion-impossibility finding (AGENT_PLAN §5.3): fusion serves breadth,
the chunk backbone serves unique reach (e.g. un-extracted Vanrafia ranks chunk-6 but span-keyed-fused
33), so taking BOTH legs' top-10 keeps neither failure mode in the agent's blind spot.

:class:`CorpusRetriever` is the ``types.RetrieverSeam`` the loop drives: one ``retrieve(sub_queries)``
per iteration, fanning ``corpus_retrieve`` out over the sub-queries and unioning by span
(``corpus_retrieve`` costs zero LLM requests, §5.1, so the fan-out is free).
"""

from src.agent.types import EvidenceItem
from src.rag.fusion import K_RRF, rrf_fuse_by_span

CORPUS_RETRIEVE_K = 10  # FIXED per §5.3 — depth is not agent-controllable.


def corpus_retrieve(query: str, chunk_retriever, entity_retriever) -> list[EvidenceItem]:
    """chunk@10 ∪ fused@10, span-deduped, each carrying chunk text + (doc_id, line_range). ≤20 spans."""
    ru_chunk = [u for u, _ in chunk_retriever.retrieve(query, len(chunk_retriever.units))]
    ru_entity = [u for u, _ in entity_retriever.retrieve(query, len(entity_retriever.units))]

    chunk_top = ru_chunk[:CORPUS_RETRIEVE_K]
    fused_top = rrf_fuse_by_span([ru_chunk, ru_entity], K_RRF)[:CORPUS_RETRIEVE_K]

    # Chunk text by span (the chunk leg indexes the FULL corpus, so every span — including a fused
    # rep, which co-locates with its chunk — resolves to chunk text per §5.3; entity-only fallback).
    chunk_text = {(u.doc_id, u.line_range): u.text for u in ru_chunk}

    out: list[EvidenceItem] = []
    seen: set[tuple[str, tuple[int, int]]] = set()
    for u in (*chunk_top, *fused_top):
        key = (u.doc_id, u.line_range)
        if key in seen:
            continue
        seen.add(key)
        out.append(EvidenceItem(text=chunk_text.get(key, u.text), doc_id=u.doc_id, line_range=u.line_range))
    return out


class CorpusRetriever:
    """RetrieverSeam over the corpus tool: fan ``corpus_retrieve`` over a query's sub-queries, union by span."""

    def __init__(self, chunk_retriever, entity_retriever) -> None:
        self.chunk = chunk_retriever
        self.entity = entity_retriever

    def retrieve(self, sub_queries: list[str]) -> list[EvidenceItem]:
        out: list[EvidenceItem] = []
        seen: set[tuple[str, tuple[int, int]]] = set()
        for q in sub_queries:
            for item in corpus_retrieve(q, self.chunk, self.entity):
                key = (item.doc_id, item.line_range)
                if key not in seen:
                    seen.add(key)
                    out.append(item)
        return out


def build_corpus_retriever() -> CorpusRetriever:
    """Wire the committed Phase 3 retrievers (loads the persisted FAISS indexes from gitignored data/rag/)."""
    from src.rag.chunk_leg import build_or_load
    from src.rag.entity_leg import build_or_load_entity

    return CorpusRetriever(build_or_load(), build_or_load_entity())
