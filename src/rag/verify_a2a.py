"""A2a gate — eyeball that the chunk-leg retriever returns SANE ranked units.

NOT scored (no recall@k — that is A2b/Gate A). For three golden queries it prints the top-5
returned chunk units' line_ranges + a snippet, and a yes/no on whether the chunk that
*contains the golden answer span* is in the top-5. The yes/no is an eyeball, not a metric;
a "no" is a real signal about retrieval quality, reported plainly — nothing is tuned to pass.
Also reports the embedding model, index size/path + reload check, and that BM25 tokenization
preserved a drug-code token (the silent-failure the eyeball guards against).
"""

import json
from pathlib import Path

from .chunk_leg import INDEX_DIR, build_or_load
from .dense import INDEX_FILE, META_FILE, DenseIndex
from .embeddings import Embedder
from .sparse import tokenize

_GOLDEN = Path("src/evals/golden/retrieval.golden.json")
_EYEBALL = ["Q8", "Q7", "Q4"]


def _target_spans(q: dict) -> list[tuple[str, tuple[int, int]]]:
    """(doc_id, line_range) answer spans whose containing chunk we hope to see in top-5."""
    spans: list[tuple[str, tuple[int, int]]] = []
    for f in q.get("facts", []):
        for s in f.get("spans", []):
            if s.get("resolution") != "resolution_limited":  # eyeball against the CLEAN location
                spans.append((s["doc_id"], (s["line_range"][0], s["line_range"][1])))
    for r in q.get("aggregate", {}).get("row_set", []):
        spans.append((r["doc_id"], (r["line_range"][0], r["line_range"][1])))
    return spans


def _containing_chunks(units, doc_id: str, span: tuple[int, int]) -> set[tuple[str, tuple[int, int]]]:
    a, b = span
    return {(u.doc_id, u.line_range) for u in units
            if u.doc_id == doc_id and u.line_range[0] <= a and b <= u.line_range[1]}


def _snippet(text: str, n: int = 110) -> str:
    return " ".join(text.split())[:n]


def main() -> None:
    retr = build_or_load()
    golden = {q["id"]: q for q in json.loads(_GOLDEN.read_text(encoding="utf-8"))["queries"]}

    # --- machinery report ---
    idx_path = INDEX_DIR / INDEX_FILE
    meta = json.loads((INDEX_DIR / META_FILE).read_text(encoding="utf-8"))
    reload_ok = DenseIndex.load(INDEX_DIR, Embedder(meta["embed_model"])).index.ntotal == retr.dense.index.ntotal
    print("A2a chunk-leg retriever — eyeball verification (NOT scored)\n")
    print(f"  embed_model    : {meta['embed_model']}  (dim {meta['dim']})")
    print(f"  corpus         : {meta['num_units']} chunk units  ({', '.join(Path(p).name for p in meta['docs'])})")
    print(f"  chunk_config   : {meta['chunk_config']}   k_rrf={meta['k_rrf']}   metric={meta['metric']}")
    print(f"  faiss index    : {idx_path}  ({idx_path.stat().st_size/1024:.0f} KB, ntotal={retr.dense.index.ntotal})")
    print(f"  reloads OK     : {reload_ok}")
    sample = "TAK-861 VAYHIA Lp(a) iptacopan P-III 1/2"
    print(f"  bm25 tokenize  : {sample!r} -> {tokenize(sample)}\n")

    # --- per-query eyeball ---
    for qid in _EYEBALL:
        q = golden[qid]
        targets = _target_spans(q)
        target_chunks: set[tuple[str, tuple[int, int]]] = set()
        for doc, sp in targets:
            target_chunks |= _containing_chunks(retr.units, doc, sp)
        top = retr.retrieve(q["query"], k=5)
        top_keys = [(u.doc_id, u.line_range) for u, _ in top]
        hit = any(tc in top_keys for tc in target_chunks)
        print(f"== {qid} [{q['type']}] {q['query']}")
        print(f"   golden answer in chunk(s): {sorted((d, lr) for d, lr in target_chunks)}")
        for rank, (u, score) in enumerate(top, 1):
            mark = "  <-- contains golden span" if (u.doc_id, u.line_range) in target_chunks else ""
            print(f"   {rank}. {u.doc_id} L{u.line_range[0]}-{u.line_range[1]}  rrf={score:.4f}{mark}")
            print(f"      “{_snippet(u.text)}”")
        print(f"   EYEBALL: golden-containing chunk in top-5? {'YES' if hit else 'NO'}\n")


if __name__ == "__main__":
    main()
