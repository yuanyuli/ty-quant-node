import json

from ty_quant_node.backend.market import export_qlib
from ty_quant_node.data.pit_adjustment import build_pit_adjustment, derive_vendor_events
from ty_quant_node.factors.compute import compute_ty_factors
from ty_quant_node.nodes import QlibDataset, QlibModel, QlibPredict, QlibTrain


def test_ty_factors_compute_from_pit_provider(tmp_path, market_frame):
    provider = tmp_path / "provider"
    pit = build_pit_adjustment(market_frame, derive_vendor_events(market_frame), snapshot_id="fixture")
    export_qlib(pit, provider, adjustment="pit")
    handle = compute_ty_factors(provider, factor_set="ty_factors", output_dir=tmp_path / "factors")
    assert handle.kind == "QLIB_FEATURE_SET"
    features = __import__("pandas").read_parquet(tmp_path / "factors" / "features.parquet")
    assert {"TY_MOM_5", "TY_MOM_20", "TY_VOL_20", "TY_VOLUME_RATIO_20"}.issubset(features.columns)
    assert features["TY_MOM_5"].notna().sum() == 2
    manifest = json.loads((tmp_path / "factors" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["factor_set"] == "ty_factors"


def test_ty_factor_cache_reuses_same_provider_version(tmp_path, market_frame):
    provider = tmp_path / "provider"
    pit = build_pit_adjustment(market_frame, derive_vendor_events(market_frame), snapshot_id="fixture")
    export_qlib(pit, provider, adjustment="pit")
    first = compute_ty_factors(provider, output_dir=tmp_path / "factors")
    second = compute_ty_factors(provider, output_dir=tmp_path / "factors")
    assert first.metadata["cache_key"] == second.metadata["cache_key"]


def test_alpha158_profile_uses_qlib_standard_provider_fields(tmp_path, market_frame):
    provider = tmp_path / "provider"
    export_qlib(market_frame, provider, adjustment="qfq")
    handle = compute_ty_factors(provider, factor_set="alpha158", output_dir=tmp_path / "alpha158")
    assert handle.metadata["factor_count"] == 158
    features = __import__("pandas").read_parquet(tmp_path / "alpha158" / "features.parquet")
    assert {"KMID", "OPEN0", "VSUMD60"}.issubset(features.columns)


def test_ty_feature_set_flows_into_dataset_train_and_predict(tmp_path, market_frame):
    provider = tmp_path / "provider"
    export_qlib(market_frame, provider, adjustment="qfq")
    feature_handle = compute_ty_factors(
        provider,
        factor_set="custom",
        custom={"TY_CLOSE_COPY": {"expression": "$ty_close", "inputs": ["ty_close"], "lookback": 0}},
        output_dir=tmp_path / "factors",
    )
    dataset_handle = QlibDataset().run(
        {"kind": "QLIB_EXPORT", "version": "1", "path": str(provider)},
        "2024-01-01", "2024-01-04", "2024-01-05", "2024-01-06",
        feature_handle,
        1,
    )[0]
    model_handle = QlibModel().run("linear", "{}")[0]
    trained, _ = QlibTrain().run(dataset_handle, model_handle, str(tmp_path / "model"), feature_handle)
    signal = QlibPredict().run(trained, dataset_handle, "test", feature_handle)[0]
    assert signal["kind"] == "QLIB_SIGNAL_TABLE"
