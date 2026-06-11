"""Stage-A chunk-leg retriever: dense (FAISS) + BM25, fused by RRF -> ranked chunk units.

This is the callable Stage A2b will feed into the shared scorer (``retrieval_scorer.py``).
The corpus is **every chunk of both reports** (Takeda 34 + Novartis 100) — the chunk leg is
the reachability backbone, so it indexes the full corpus regardless of what extraction
touched (this is how it can reach un-extracted regions like Vanrafia's). Retrieval chunking
reuses the ingestion chunker at the locked **1500/200** config (whether finer units are
justified is a Gate-A decision on data, not now).
"""

from pathlib import Path

from src.ingestion.chunker import ChunkConfig, chunk_document
from src.ingestion.loader import load_report

from .dense import INDEX_FILE, DenseIndex, build_and_persist
from .embeddings import Embedder
from .fusion import K_RRF, rrf
from .sparse import BM25Index
from .units import RetrievalUnit

# Corpus registry (mirrors src/evals/run.py _DOCS).
_DOCS = [
    {"path": "data/reports/qr2025_q4_Pipeline_table_en.md", "source_company": "Takeda", "doc_type": "pipeline_table"},
    {"path": "data/reports/q1-2026-interim-financial-report-en.md", "source_company": "Novartis", "doc_type": "financial_report"},
]
RETRIEVAL_CHUNK_CONFIG = ChunkConfig(chunk_size=1500, overlap=200)  # locked: reuse extraction config
INDEX_DIR = Path("data/rag")  # gitignored (data/)


def build_chunk_corpus(config: ChunkConfig = RETRIEVAL_CHUNK_CONFIG) -> list[RetrievalUnit]:
    """Chunk both reports into leg-agnostic ``RetrievalUnit``s (kind='chunk')."""
    units: list[RetrievalUnit] = []
    for d in _DOCS:
        loaded = load_report(d["path"], source_company=d["source_company"], doc_type=d["doc_type"])
        for ch in chunk_document(loaded, config):
            units.append(RetrievalUnit(
                doc_id=ch.document_id,
                line_range=(ch.line_range[0], ch.line_range[1]),
                text=ch.text,
                kind="chunk",
                payload={"chunk_index": ch.chunk_index, "section_path": list(ch.section_path)},
            ))
    return units


class ChunkLegRetriever:
    """dense + BM25 -> RRF -> ranked chunk units. ``retrieve`` returns top-k (unit, rrf_score)."""

    def __init__(self, units: list[RetrievalUnit], dense: DenseIndex, bm25: BM25Index, k_rrf: int = K_RRF) -> None:
        self.units = units
        self.dense = dense
        self.bm25 = bm25
        self.k_rrf = k_rrf

    def retrieve(self, query: str, k: int = 5) -> list[tuple[RetrievalUnit, float]]:
        n = len(self.units)
        dense_ranked = [i for i, _ in self.dense.search(query, n)]
        bm25_ranked = [i for i, _ in self.bm25.rank(query)]
        fused = rrf([dense_ranked, bm25_ranked], self.k_rrf)
        return [(self.units[i], score) for i, score in fused[:k]]


def build_or_load(index_dir: str | Path = INDEX_DIR, rebuild: bool = False) -> ChunkLegRetriever:
    """Build+persist the dense index if absent (or ``rebuild``), then load the retriever.

    Units come from the persisted ``units.json`` (via ``DenseIndex.load``) so FAISS rows and
    BM25 rows index the same corpus — one source of truth.
    """
    embedder = Embedder()
    index_dir = Path(index_dir)
    if rebuild or not (index_dir / INDEX_FILE).exists():
        units = build_chunk_corpus()
        build_and_persist(units, embedder, index_dir, extra_meta={
            "chunk_config": {"chunk_size": RETRIEVAL_CHUNK_CONFIG.chunk_size, "overlap": RETRIEVAL_CHUNK_CONFIG.overlap},
            "docs": [d["path"] for d in _DOCS],
            "k_rrf": K_RRF,
        })
    dense = DenseIndex.load(index_dir, embedder)
    bm25 = BM25Index(dense.units)
    return ChunkLegRetriever(dense.units, dense, bm25)
