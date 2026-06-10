"""Tests for src/evals/normalize.py — text, slug parity, fuzzy, value scale."""

from src.evals import normalize as N
from src.extraction.extractor import _slug as extractor_slug


def test_slug_parity_with_extractor():
    # The eval slug MUST equal the extractor's so golden identifiers align with
    # fact asset_ids already produced by the extractor.
    for s in ["VAY736", "TAK-279", "zasocitinib", "Ta s i g n a", "Tafinlar + Mekinist", "  "]:
        assert N.slug(s) == extractor_slug(s)


def test_canonical_term_folds_indication_synonyms():
    # The real divergence: Takeda "Immunoglobulin A nephropathy" vs Novartis "IgA nephropathy".
    assert N.canonical_term("IgA nephropathy") == N.canonical_term("Immunoglobulin A nephropathy")
    assert N.canonical_term("IgAN") == N.canonical_term("Immunoglobulin A nephropathy")
    assert N.canonical_term("SLE") == N.canonical_term("Systemic lupus erythematosus")
    assert N.canonical_term("wAIHA") == N.canonical_term("Warm autoimmune hemolytic anemia")


def test_canonical_term_british_american_fold():
    assert N.canonical_term("Coeliac disease") == N.canonical_term("Celiac disease")
    assert N.canonical_term("Paediatric tumour") == N.canonical_term("pediatric tumor")


def test_fuzzy_match_accepts_variants_rejects_distinct():
    assert N.fuzzy_match("Warm autoimmune hemolytic anemia", "wAIHA")
    assert N.fuzzy_match("Ulcerative Colitis", "ulcerative colitis")
    # genuinely different indications must NOT merge
    assert not N.fuzzy_match("gastric cancer", "gastrointestinal stromal tumor")
    assert not N.fuzzy_match("Huntington's disease", "Alzheimer's disease")


def test_value_scale_and_match():
    assert N.unit_scale("USD billion") == 1e9
    assert N.unit_scale("USD millions") == 1e6
    assert N.to_base(1.3, "billion") == 1.3e9
    # 1.3 billion vs 1305 million -> within 2% rounding tolerance
    assert N.values_match(1.3, "billion", 1305, "million")
    assert N.values_match(184, "million", 184, "USD million")
    # genuinely different magnitudes do not match
    assert not N.values_match(184, "million", 642, "million")
    assert not N.values_match(1.3, "billion", 1.3, "million")


def test_metric_dimension():
    assert N.metric_dimension("revenue") == "currency"
    assert N.metric_dimension("growth_rate") == "percent"
    assert N.metric_dimension("country_count") == "count"


def test_agency_attribute_pmda_mhlw_fold():
    # Policy (d): PMDA == MHLW for attribute scoring (same JP jurisdiction).
    assert N.agency_attribute_matches("PMDA", "MHLW")
    assert N.agency_attribute_matches("FDA", "FDA")
    assert not N.agency_attribute_matches("FDA", "EMA")
    assert not N.agency_attribute_matches("MHLW", "other")  # declined agency = attribute error
