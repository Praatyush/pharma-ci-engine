"""Stage-B entity leg (LEAN) — a RetrievalUnit over each persisted extraction FACT, retrieved by the
**identical** mechanism as the chunk leg (same fastembed model, same FAISS approach, same BM25
tokenizer, same RRF). Structural parity is the point: a null result must mean "entity-awareness
doesn't help here," not "the leg was crippled."

§B.1 — entity units are **chunk-grained**: ``line_range = fact.source_ref.line_range`` (the chunk the
fact was extracted from). So the entity leg cannot localize finer than the chunk leg; its only
possible contribution is **reranking/recall** — a serialized structured fact concentrates the signal
a mashed table scatters, so it may rank a buried-but-extracted fact higher than diluted chunk text
does. Built over **extracted facts only** (that is all that exists — which is why entity-only is
structurally 0 on un-extracted content like Vanrafia).

Serialization is the **lossy variable** — a single reasonable, **un-tuned** scheme; measured as-is,
flagged in the Gate-B report, never optimized.
"""

from pathlib import Path

from src.extraction.persistence import load_extraction

from .dense import INDEX_FILE, DenseIndex, build_and_persist
from .embeddings import Embedder
from .fusion import K_RRF, rrf
from .sparse import BM25Index
from .units import RetrievalUnit

_ARTIFACTS = [
    "data/eval/extractions/qr2025_q4_Pipeline_table_en.extraction.json",
    "data/eval/extractions/q1-2026-interim-financial-report-en.slice.extraction.json",
]
ENTITY_INDEX_DIR = Path("data/rag/entity")  # gitignored (data/); separate from the chunk index

# The un-tuned serialization scheme (the lossy variable). One reasonable field order per fact type,
# nulls omitted. NOT optimized — a single scheme measured as-is.
SERIALIZATION = "asset | indication | region | stage  (/ action / phase / value, per type; nulls omitted)"


def _asset_tokens(asset_id: str | None, lookup: dict) -> str:
    """Resolve an asset_id slug to its human identifiers (generic/codes/brands/aliases), else the slug."""
    a = lookup.get(asset_id)
    if a is None:
        return asset_id or ""
    toks = [t for t in ([a.generic_name] + list(a.development_codes) + list(a.brand_names) + list(a.aliases)) if t]
    return " ".join(toks) if toks else (asset_id or "")


def _join(*fields: object) -> str:
    return " | ".join(str(f) for f in fields if f)


def serialize(kind: str, fact: object, lookup: dict) -> str:
    if kind == "program":
        return _join(_asset_tokens(fact.asset_id, lookup), fact.indication, fact.region, fact.stage, fact.therapeutic_area)
    if kind == "regulatory_event":
        return _join(_asset_tokens(fact.asset_id, lookup), fact.indication, fact.region, fact.action, fact.agency)
    if kind == "trial":
        assets = " ".join(_asset_tokens(a, lookup) for a in fact.asset_ids) if fact.asset_ids else ""
        return _join(assets, fact.indication, f"phase {fact.phase}" if fact.phase else "", fact.trial_name)
    if kind == "market_metric":
        subj = _asset_tokens(fact.subject, lookup) if fact.subject in lookup else fact.subject
        return _join(subj, fact.metric, fact.geography, f"{fact.value} {fact.unit}" if fact.value is not None else "")
    return ""


def build_entity_corpus() -> list[RetrievalUnit]:
    """One RetrievalUnit per extraction FACT (programs/trials/reg-events/metrics), both documents."""
    units: list[RetrievalUnit] = []
    for path in _ARTIFACTS:
        _, res = load_extraction(path)
        lookup = {a.id: a for a in res.assets}
        groups = [("program", res.programs), ("trial", res.trials),
                  ("regulatory_event", res.regulatory_events), ("market_metric", res.market_metrics)]
        for kind, items in groups:
            for fact in items:
                text = serialize(kind, fact, lookup)
                if not text.strip():
                    continue
                sr = fact.source_ref
                units.append(RetrievalUnit(
                    doc_id=sr.document_id,
                    line_range=(sr.line_range[0], sr.line_range[1]),
                    text=text,
                    kind=f"fact:{kind}",
                    payload={
                        "asset_id": getattr(fact, "asset_id", None) or getattr(fact, "subject", None),
                        "indication": getattr(fact, "indication", None),
                        "stage": getattr(fact, "stage", None),
                        "action": getattr(fact, "action", None),
                    },
                ))
    return units


class EntityLegRetriever:
    """Mirror of ChunkLegRetriever — dense + BM25 -> RRF over the entity (serialized-fact) corpus."""

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


def build_or_load_entity(index_dir: str | Path = ENTITY_INDEX_DIR, rebuild: bool = False) -> EntityLegRetriever:
    embedder = Embedder()
    index_dir = Path(index_dir)
    if rebuild or not (index_dir / INDEX_FILE).exists():
        units = build_entity_corpus()
        build_and_persist(units, embedder, index_dir, extra_meta={
            "leg": "entity", "serialization": SERIALIZATION, "artifacts": _ARTIFACTS, "k_rrf": K_RRF,
        })
    dense = DenseIndex.load(index_dir, embedder)
    bm25 = BM25Index(dense.units)
    return EntityLegRetriever(dense.units, dense, bm25)
