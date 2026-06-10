"""Tests for src/evals/matching.py — asset clustering, collapse, match alignment."""

from src.evals import matching as M
from src.evals.labels import GoldenAsset, GoldenProgram, GoldenRegulatoryEvent
from src.extraction.extractor import ExtractionResult
from src.schema import Asset, Program, RegulatoryEvent, SourceRef


def _sr() -> SourceRef:
    return SourceRef(document_id="d", line_range=(1, 2), snippet="x")


def _asset(id_, **kw) -> Asset:
    kw.setdefault("company", "Novartis")
    return Asset(id=id_, **kw)


def _program(asset_id, indication, region, stage) -> Program:
    return Program(
        id=f"p:{asset_id}:{indication}", asset_id=asset_id, therapeutic_area="immunology",
        indication=indication, region=region, stage=stage, as_of_date="2026-03-31", source_ref=_sr(),
    )


def _reg(asset_id, action, indication, region, agency) -> RegulatoryEvent:
    return RegulatoryEvent(
        asset_id=asset_id, agency=agency, region=region, action=action,
        indication=indication, source_ref=_sr(),
    )


def test_asset_index_merges_surface_forms():
    # one asset carries both forms -> bridges the two slugs into one molecule.
    assets = [
        _asset("ianalumab", generic_name="ianalumab", development_codes=["VAY736"]),
        _asset("vay736", development_codes=["VAY736"]),
        _asset("ianalumab", generic_name="ianalumab"),
        _asset("remibrutinib", generic_name="remibrutinib"),
    ]
    idx = M.build_asset_index(assets)
    assert idx.num_clusters == 2  # {ianalumab, vay736} and {remibrutinib}
    assert idx.resolve("ianalumab") == idx.resolve("vay736")
    assert "vay736" in idx.cluster_slugs("ianalumab")


def test_collapse_folds_duplicates_including_cross_slug_assets():
    result = ExtractionResult(
        assets=[
            _asset("ianalumab", generic_name="ianalumab", development_codes=["VAY736"]),
            _asset("vay736", development_codes=["VAY736"]),
            _asset("ianalumab", generic_name="ianalumab"),
        ],
        programs=[
            _program("ianalumab", "Systemic lupus erythematosus", "Global", "P3"),
            _program("ianalumab", "Systemic lupus erythematosus", "Global", "P3"),  # exact dup
            _program("ianalumab", "SLE", "Global", "P3"),  # synonym dup -> same key
        ],
        regulatory_events=[
            _reg("ianalumab", "breakthrough", "Sjogren's disease", "US", "FDA"),
            _reg("vay736", "breakthrough", "Sjogren's disease", "US", "FDA"),  # cross-slug dup
        ],
    )
    collapsed = M.collapse(result)
    summary = collapsed.summary()
    assert summary["assets"] == (3, 1)            # 3 raw -> 1 molecule
    assert summary["programs"] == (3, 1)          # synonym + exact dups fold
    assert summary["regulatory_events"] == (2, 1)  # ianalumab == vay736 -> one event


def test_match_lists_aligns_predicted_to_golden():
    pred_assets = [_asset("ianalumab", generic_name="ianalumab", development_codes=["VAY736"])]
    pidx = M.build_asset_index(pred_assets)
    gidx = M.build_golden_asset_index([GoldenAsset(identifiers=["ianalumab", "VAY736"])])

    predicted = [
        _program("vay736", "SLE", "Global", "P3"),          # matches golden via cluster + synonym
        _program("remibrutinib", "Urticaria", "US", "P2"),  # false positive
    ]
    golden = [
        GoldenProgram(asset="ianalumab", indication="Systemic lupus erythematosus",
                      region="Global", stage="P3"),
        GoldenProgram(asset="ianalumab", indication="Lupus nephritis", region="EU", stage="P2"),  # miss
    ]
    out = M.match_lists(predicted, golden, "programs", pidx, gidx)
    assert len(out.matched) == 1
    assert len(out.false_positives) == 1
    assert len(out.misses) == 1


def test_key_incomplete_separated_from_false_positive():
    # A predicted reg-event with indication='not specified' is under-specified (key-incomplete),
    # NOT a clean false positive; the golden it under-specifies stays a miss.
    pidx = M.build_asset_index([_asset("ianalumab", generic_name="ianalumab")])
    gidx = M.build_golden_asset_index([GoldenAsset(identifiers=["ianalumab"])])
    predicted = [
        _reg("ianalumab", "breakthrough", "not specified", "US", "FDA"),  # key-incomplete
        _reg("ianalumab", "orphan", "Lupus", "US", "FDA"),                # clean FP (keyable)
    ]
    golden = [GoldenRegulatoryEvent(asset="ianalumab", action="breakthrough", indication="Sjogren's disease",
                                    region="US", agency="FDA", from_progress_row=False)]
    out = M.match_lists(predicted, golden, "regulatory_events", pidx, gidx)
    assert not out.matched
    assert len(out.misses) == 1                 # golden designation stays a miss
    assert len(out.key_incomplete) == 1         # the 'not specified' one
    assert len(out.false_positives) == 1        # the keyable Lupus one


def test_regevent_match_ignores_agency_uses_region():
    # agency demoted: predicted agency 'other' but region JP still matches golden PMDA/JP.
    pidx = M.build_asset_index([_asset("tak-861", development_codes=["TAK-861"])])
    gidx = M.build_golden_asset_index([GoldenAsset(identifiers=["TAK-861"])])
    predicted = [_reg("tak-861", "filed", "Narcolepsy type 1", "JP", "other")]
    golden = [GoldenRegulatoryEvent(asset="TAK-861", action="filed", indication="Narcolepsy type 1",
                                    region="JP", agency="PMDA", from_progress_row=True)]
    out = M.match_lists(predicted, golden, "regulatory_events", pidx, gidx)
    assert len(out.matched) == 1 and not out.misses
