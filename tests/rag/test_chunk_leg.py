"""A2a unit tests for the deterministic, model-free pieces — the silent-failure modes the
eyeball guards against: BM25 tokenization must keep drug codes/acronyms whole, and RRF must
combine ranks correctly (incl. a unit present in only one leg's list). The embedding/FAISS
path is exercised by the eyeball harness (``src/rag/verify_a2a.py``), not here (needs the model)."""

from src.rag.fusion import rrf
from src.rag.sparse import tokenize


def test_tokenize_preserves_drug_codes_and_acronyms():
    toks = tokenize("TAK-861 and VAYHIA in P-III; ianalumab; phase 1/2")
    assert "tak-861" in toks      # dev code stays whole (not tak + 861)
    assert "vayhia" in toks       # acronym survives
    assert "ianalumab" in toks
    assert "p-iii" in toks        # hyphen kept
    assert "1/2" in toks          # slash kept


def test_tokenize_lowercases_but_keeps_signal():
    assert tokenize("Lp(a)") == ["lp(a)"]     # parens kept (Lp(a) is one signal token)
    assert tokenize("TYK2") == ["tyk2"]


def test_rrf_orders_by_summed_reciprocal_rank():
    # doc 7 is rank-1 in both legs -> highest; doc 9 only in leg B -> contributes one term.
    dense = [7, 3, 9]
    bm25 = [7, 9, 3]
    fused = dict(rrf([dense, bm25], k_rrf=60))
    # 7: 1/61 + 1/61 ; 3: 1/62 + 1/63 ; 9: 1/63 + 1/62  -> 7 first
    assert max(fused, key=fused.get) == 7
    assert set(fused) == {7, 3, 9}


def test_rrf_unit_in_only_one_list_contributes_one_term():
    fused = dict(rrf([[1], [2]], k_rrf=60))
    assert fused[1] == 1.0 / 61 and fused[2] == 1.0 / 61   # each present once, no penalty/imputation
