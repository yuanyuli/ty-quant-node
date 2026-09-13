"""ComfyUI 节点适配层。节点之间只传递版本化轻量句柄。"""

import json
import hashlib
from pathlib import Path
import re
import pandas as pd

from .core.handles import Handle
from .data import apply_adjustment
from .data.pit_adjustment import build_pit_adjustment, derive_vendor_events
from .data.tushare_source import TushareDailySource
from .backend.market import export_qlib, normalize_market_frame
from .backend.qlib_backend import build_dataset_from_export, build_dataset_from_feature_set
from .backend.model_backend import ModelSpec, train_model, predict_model, load_model
from .backend.backtest_backend import backtest, BacktestResult
from .core.report import create_report, image_to_tensor
from .factors.compute import compute_ty_factors


def _handle(value) -> Handle:
    return value if isinstance(value, Handle) else Handle.from_dict(value)


def _control_values(value) -> dict:
    if value is None:
        return {}
    control = _handle(value)
    if control.kind != "QLIB_CONTROL":
        raise ValueError(f"control 输入类型错误: {control.kind}")
    return dict(control.metadata)


def _controlled(values: dict, key: str, fallback):
    value = values.get(key, fallback)
    return fallback if value in (None, "") else value


def _versioned_target(base_dir: str | Path, snapshot_id: str) -> Path:
    """选择不会覆盖已有 snapshot 的 artifact 目录。"""
    base = Path(base_dir).resolve()
    manifest_path = base / "manifest.json"
    if not manifest_path.exists():
        if any((base / name).exists() for name in ("raw.parquet", "dataset.parquet", "features")):
            return base / snapshot_id
        return base
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base / snapshot_id
    if str(existing.get("snapshot_id")) == str(snapshot_id):
        return base
    return base / snapshot_id


def _stable_frame_hash(frame: pd.DataFrame) -> str:
    stable = frame.drop(columns=["asof"], errors="ignore").copy()
    if not stable.empty:
        stable = stable.sort_values(sorted(stable.columns)).sort_index(axis=1).reset_index(drop=True)
    payload = stable.to_json(date_format="iso", orient="records")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_json_hash(value) -> str:
    payload = json.dumps(value or [], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_date_range_inputs(values: tuple[str, ...]) -> None:
    supplied = [bool(str(value or "").strip()) for value in values]
    if any(supplied) and not all(supplied):
        raise ValueError("训练和测试区间必须同时填写开始和结束日期")
    if not all(supplied):
        return
    starts_ends = [pd.Timestamp(str(value)) for value in values]
    if starts_ends[0] > starts_ends[1] or starts_ends[2] > starts_ends[3]:
        raise ValueError("训练或测试区间的开始日期不能晚于结束日期")
    if starts_ends[1] >= starts_ends[2]:
        raise ValueError("训练结束日期必须早于测试开始日期")


class TushareConfig:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "token_source": (["environment"],),
                "token_env_name": ("STRING", {"default": "TUSHARE_TOKEN", "multiline": False}),
                "retries": ("INT", {"default": 3, "min": 1, "max": 5}),
            }
        }

    RETURN_TYPES = ("TUSHARE_CONFIG",)
    RETURN_NAMES = ("Tushare 配置",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Data"

    def run(self, token_source="environment", token_env_name="TUSHARE_TOKEN", retries=3):
        # 兼容早期 run("environment", 3) 调用，避免旧工作流脚本失效。
        if isinstance(token_env_name, (int, float)) and retries == 3:
            retries, token_env_name = int(token_env_name), "TUSHARE_TOKEN"
        if token_source != "environment":
            raise ValueError("Tushare 目前只支持从环境变量读取 token")
        token_env_name = str(token_env_name or "").strip()
        if not token_env_name:
            raise ValueError("token_env_name 不能为空")
        return (
            Handle(
                "TUSHARE_CONFIG",
                "",
                metadata={"token_source": token_source, "token_env_name": token_env_name, "retries": int(retries)},
            ).to_dict(),
        )


class QlibControl:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "csv_path": ("STRING", {"default": ""}),
                "adjustment": (["qfq", "hfq", "none"],),
                "output_root": ("STRING", {"default": "outputs/ty_quant"}),
                "train_start": ("STRING", {"default": ""}),
                "train_end": ("STRING", {"default": ""}),
                "test_start": ("STRING", {"default": ""}),
                "test_end": ("STRING", {"default": ""}),
                "model_type": (["linear", "lightgbm"],),
                "params_json": ("STRING", {"default": "{}"}),
                "artifact_dir": ("STRING", {"default": "outputs/ty_quant/model"}),
                "segment": (["train", "valid", "test"],),
                "topk": ("INT", {"default": 1, "min": 1}),
                "n_drop": ("INT", {"default": 0, "min": 0}),
                "transaction_cost_bps": ("FLOAT", {"default": 5.0, "min": 0.0}),
                "report_dir": ("STRING", {"default": "outputs/ty_quant/report"}),
            }
        }

    RETURN_TYPES = ("QLIB_CONTROL",)
    RETURN_NAMES = ("控制配置",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Control"

    def run(
        self,
        csv_path,
        adjustment,
        output_root,
        train_start,
        train_end,
        test_start,
        test_end,
        model_type,
        params_json,
        artifact_dir,
        segment,
        topk=1,
        n_drop=0,
        transaction_cost_bps=5.0,
        report_dir="",
    ):
        try:
            params = json.loads(params_json or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("QlibControl 参数 JSON 无效") from exc
        if not isinstance(params, dict):
            raise RuntimeError("QlibControl 参数 JSON 必须是对象")
        metadata = {
            "csv_path": str(csv_path),
            "adjustment": str(adjustment),
            "output_root": str(output_root),
            "train_start": str(train_start),
            "train_end": str(train_end),
            "test_start": str(test_start),
            "test_end": str(test_end),
            "model_type": str(model_type),
            "params_json": json.dumps(params, ensure_ascii=False, sort_keys=True),
            "params": params,
            "artifact_dir": str(artifact_dir),
            "segment": str(segment),
            "topk": int(topk),
            "n_drop": int(n_drop),
            "transaction_cost_bps": float(transaction_cost_bps),
            "report_dir": str(report_dir),
        }
        return (Handle("QLIB_CONTROL", "", metadata=metadata).to_dict(),)


class QlibRuntime:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"provider_uri": ("STRING", {"default": ""}), "region": (["cn", "us"],), "seed": ("INT", {"default": 42, "min": 0}), "experiment_uri": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("QLIB_RUNTIME",)
    RETURN_NAMES = ("Qlib 运行时",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Qlib"

    def run(self, provider_uri, region="cn", seed=42, experiment_uri=""):
        import random
        import numpy as np
        path = str(Path(provider_uri).resolve()) if provider_uri else ""
        try:
            import qlib
        except ModuleNotFoundError as exc:
            if exc.name != "qlib":
                raise
            return (Handle("QLIB_RUNTIME", path, metadata={"region": region, "seed": int(seed), "experiment_uri": experiment_uri, "qlib_version": "unavailable", "dataset_backend": "compat"}).to_dict(),)

        qlib.init(provider_uri=path or None, region=region, dataset_cache=None, expression_cache=None, clear_mem_cache=True)
        random.seed(int(seed))
        np.random.seed(int(seed))
        return (Handle("QLIB_RUNTIME", path, metadata={"region": region, "seed": int(seed), "experiment_uri": experiment_uri, "qlib_version": getattr(qlib, "__version__", "unknown")}).to_dict(),)


class TushareDailyFetch:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("TUSHARE_CONFIG",),
                "ts_codes": ("STRING", {"default": "000001.SZ", "multiline": True}),
                "start_date": ("STRING", {"default": "20240101"}),
                "end_date": ("STRING", {"default": "20241231"}),
                "snapshot_dir": ("STRING", {"default": "outputs/ty_quant/snapshots"}),
            },
            "optional": {"include_events": ("BOOLEAN", {"default": True})},
        }

    RETURN_TYPES = ("MARKET_DATA",)
    RETURN_NAMES = ("行情快照",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Data"

    def run(self, config, ts_codes, start_date, end_date, snapshot_dir, include_events=True):
        cfg = _handle(config)
        if cfg.kind != "TUSHARE_CONFIG":
            raise ValueError(f"TushareDailyFetch 输入类型错误: {cfg.kind}")
        token_env_name = str(cfg.metadata.get("token_env_name", "TUSHARE_TOKEN"))
        source = TushareDailySource(
            retries=int(cfg.metadata.get("retries", 3)),
            token_env_name=token_env_name,
        )
        codes = [code.strip().upper() for code in re.split(r"[,;\s]+", str(ts_codes or "")) if code.strip()]
        codes = list(dict.fromkeys(codes))
        if not codes:
            raise ValueError("至少提供一个股票代码")
        if not str(snapshot_dir or "").strip():
            raise ValueError("snapshot_dir 不能为空")
        data = source.fetch(codes, start_date, end_date, include_events=bool(include_events))
        events = data.attrs.get("events") or []
        snapshot_id = source.snapshot_id(data, events)
        target = _versioned_target(snapshot_dir, snapshot_id)
        target.mkdir(parents=True, exist_ok=True)
        existing_manifest = target / "manifest.json"
        if existing_manifest.exists():
            existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
            if existing.get("snapshot_id") == snapshot_id:
                return (Handle("MARKET_DATA", str(target), metadata=existing).to_dict(),)
        raw_path = target / "raw.parquet"
        data.to_parquet(raw_path, index=False)
        if events:
            pd.DataFrame(events).to_parquet(target / "events.parquet", index=False)
        manifest = {
            "schema_version": "1",
            "snapshot_id": snapshot_id,
            "source": "tushare",
            "ts_codes": codes,
            "date_range": [str(start_date), str(end_date)],
            "rows": len(data),
            "event_count": len(events),
            "include_events": bool(include_events),
            "token_env_name": token_env_name,
            "event_provenance": "tushare_dividend" if events else "none",
            "raw_hash": _stable_frame_hash(data.drop(columns=["adj_factor"], errors="ignore")),
            "factor_hash": _stable_frame_hash(data[["instrument", "datetime", "adj_factor"]]) if "adj_factor" in data else None,
            "events_hash": _stable_json_hash(events),
        }
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return (Handle("MARKET_DATA", str(target), metadata=manifest).to_dict(),)


class TushareToQlib:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "market_data": ("MARKET_DATA",),
                "adjustment_policy": (["pit", "vendor_qfq", "vendor_hfq", "none"],),
                "output_dir": ("STRING", {"default": "outputs/ty_quant/provider"}),
                "incremental": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("QLIB_EXPORT",)
    RETURN_NAMES = ("Qlib 数据",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Data"

    def run(self, market_data, adjustment_policy="pit", output_dir="", incremental=True):
        handle = _handle(market_data)
        if handle.kind != "MARKET_DATA":
            raise ValueError(f"TushareToQlib 输入类型错误: {handle.kind}")
        root = Path(handle.path).resolve()
        if not str(output_dir or "").strip():
            raise ValueError("output_dir 不能为空")
        raw_path = root / "raw.parquet"
        if not raw_path.exists():
            raise ValueError(f"MARKET_DATA 缺少 raw.parquet: {raw_path}")
        raw = pd.read_parquet(raw_path)
        manifest_path = root / "manifest.json"
        source_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        snapshot_id = str(source_manifest.get("snapshot_id") or handle.metadata.get("snapshot_id") or "snapshot")
        if adjustment_policy == "pit":
            event_path = root / "events.parquet"
            events = pd.read_parquet(event_path) if event_path.exists() else derive_vendor_events(raw)
            adjusted = build_pit_adjustment(raw, events, snapshot_id=snapshot_id)
            has_point_in_time_events = event_path.exists()
            adjusted.attrs.update(
                {
                    "point_in_time": has_point_in_time_events,
                    "adjustment_source": "tushare_dividend" if has_point_in_time_events else "vendor_adj_factor",
                    "event_count": int(len(events)),
                }
            )
            output = _versioned_target(output_dir, snapshot_id)
            existing_manifest = output / "manifest.json"
            if incremental and existing_manifest.exists():
                existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
                if existing.get("snapshot_id") == snapshot_id and existing.get("adjustment") == "pit":
                    return (Handle("QLIB_EXPORT", str(output), metadata=existing).to_dict(),)
            return (export_qlib(adjusted, output, adjustment="pit").to_dict(),)
        if adjustment_policy not in {"vendor_qfq", "vendor_hfq", "none"}:
            raise ValueError("不支持的 adjustment_policy")
        adjustment = {"vendor_qfq": "qfq", "vendor_hfq": "hfq", "none": "none"}[adjustment_policy]
        raw.attrs.update({"snapshot_id": snapshot_id, "point_in_time": False, "factor_definition": "adjusted/original", "adjustment_source": adjustment_policy})
        output = _versioned_target(output_dir, snapshot_id)
        existing_manifest = output / "manifest.json"
        if incremental and existing_manifest.exists():
            existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
            if existing.get("snapshot_id") == snapshot_id and existing.get("adjustment") == adjustment:
                return (Handle("QLIB_EXPORT", str(output), metadata=existing).to_dict(),)
        return (export_qlib(raw, output, adjustment=adjustment, allow_unadjusted=adjustment == "none").to_dict(),)


class TYFactorCompute:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "export": ("QLIB_EXPORT",),
                "factor_set": (["ty_factors", "alpha158", "selected", "custom"],),
                "selected_json": ("STRING", {"default": "[]"}),
                "custom_json": ("STRING", {"default": "[]"}),
                "output_dir": ("STRING", {"default": "outputs/ty_quant/factors"}),
            }
        }

    RETURN_TYPES = ("QLIB_FEATURE_SET", "STRING")
    RETURN_NAMES = ("因子特征", "摘要")
    FUNCTION = "run"
    CATEGORY = "TY Quant/Factors"

    def run(self, export, factor_set="ty_factors", selected_json="[]", custom_json="[]", output_dir=""):
        handle = _handle(export)
        if handle.kind != "QLIB_EXPORT":
            raise ValueError(f"TYFactorCompute 输入类型错误: {handle.kind}")
        if not str(output_dir or "").strip():
            raise ValueError("output_dir 不能为空")
        feature_handle = compute_ty_factors(
            handle.path,
            factor_set=factor_set,
            selected=selected_json,
            custom=custom_json,
            output_dir=output_dir,
        )
        summary = json.dumps(feature_handle.metadata, ensure_ascii=False)
        return feature_handle.to_dict(), summary


class AdjustPrices:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"csv_path": ("STRING", {"default": ""}), "adjustment": (["qfq", "hfq", "none"],), "output_path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("复权文件",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Data"

    def run(self, csv_path, adjustment, output_path=""):
        data = normalize_market_frame(pd.read_csv(csv_path))
        adjusted = apply_adjustment(data, adjustment)
        target = Path(output_path or f"{Path(csv_path).with_suffix('')}_{adjustment}.parquet")
        target.parent.mkdir(parents=True, exist_ok=True)
        adjusted.to_parquet(target, index=False)
        return (str(target),)


class QlibExport:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "csv_path": ("STRING", {"default": ""}),
                "adjustment": (["qfq", "hfq", "none"],),
                "output_dir": ("STRING", {"default": "outputs/ty_quant/provider"}),
            },
            "optional": {"control": ("QLIB_CONTROL",)},
        }

    RETURN_TYPES = ("QLIB_EXPORT",)
    RETURN_NAMES = ("Qlib 数据",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Qlib"

    def run(self, csv_path, adjustment, output_dir, control=None):
        values = _control_values(control)
        csv_path = _controlled(values, "csv_path", csv_path)
        adjustment = _controlled(values, "adjustment", adjustment)
        output_dir = _controlled(values, "output_root", output_dir)
        return (export_qlib(pd.read_csv(csv_path), output_dir, adjustment=adjustment).to_dict(),)


class QlibDataset:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "export": ("QLIB_EXPORT",),
                "train_start": ("STRING", {"default": ""}),
                "train_end": ("STRING", {"default": ""}),
                "test_start": ("STRING", {"default": ""}),
                "test_end": ("STRING", {"default": ""}),
            },
            "optional": {
                "features": ("QLIB_FEATURE_SET",),
                "label_horizon": ("INT", {"default": 0, "min": 0, "max": 252}),
                "control": ("QLIB_CONTROL",),
            },
        }

    RETURN_TYPES = ("QLIB_DATASET",)
    RETURN_NAMES = ("Dataset",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Qlib"

    def run(self, export, train_start="", train_end="", test_start="", test_end="", features=None, label_horizon=0, control=None):
        values = _control_values(control)
        train_start = _controlled(values, "train_start", train_start)
        train_end = _controlled(values, "train_end", train_end)
        test_start = _controlled(values, "test_start", test_start)
        test_end = _controlled(values, "test_end", test_end)
        _validate_date_range_inputs((train_start, train_end, test_start, test_end))
        handle = _handle(export)
        segments = None
        if train_start and train_end and test_start and test_end:
            segments = {"train": (train_start, train_end), "test": (test_start, test_end)}
        if features is not None:
            feature_handle = _handle(features)
            if feature_handle.kind != "QLIB_FEATURE_SET":
                raise ValueError(f"QlibDataset features 输入类型错误: {feature_handle.kind}")
            bundle = build_dataset_from_feature_set(handle.path, feature_handle.path, segments=segments, label_horizon=int(label_horizon or 0))
        else:
            bundle = build_dataset_from_export(handle.path, segments=segments)
        return (bundle.handle().to_dict(),)


class QlibModel:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"model_type": (["linear", "lightgbm"],), "params_json": ("STRING", {"default": "{}"})},
            "optional": {"control": ("QLIB_CONTROL",)},
        }

    RETURN_TYPES = ("QLIB_MODEL_SPEC",)
    RETURN_NAMES = ("模型配置",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Model"

    def run(self, model_type, params_json="{}", control=None):
        values = _control_values(control)
        model_type = _controlled(values, "model_type", model_type)
        params = values.get("params")
        if params is None:
            try:
                params = json.loads(params_json or "{}")
            except json.JSONDecodeError as exc:
                raise RuntimeError("QlibModel 参数 JSON 无效") from exc
        if not isinstance(params, dict):
            raise RuntimeError("QlibModel 参数 JSON 必须是对象")
        return (Handle("QLIB_MODEL_SPEC", "", metadata={"model_type": ModelSpec(model_type, params).model_type, "params": params}).to_dict(),)


class QlibTrain:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"dataset": ("QLIB_DATASET",), "model": ("QLIB_MODEL_SPEC",), "artifact_dir": ("STRING", {"default": "outputs/ty_quant/model"})},
            "optional": {"features": ("QLIB_FEATURE_SET",), "control": ("QLIB_CONTROL",)},
        }

    RETURN_TYPES = ("QLIB_TRAINED_MODEL", "STRING")
    RETURN_NAMES = ("训练模型", "训练摘要")
    FUNCTION = "run"
    CATEGORY = "TY Quant/Model"

    def run(self, dataset, model, artifact_dir, features=None, control=None):
        values = _control_values(control)
        artifact_dir = _controlled(values, "artifact_dir", artifact_dir)
        dataset_handle, model_handle = _handle(dataset), _handle(model)
        feature_path = dataset_handle.metadata.get("feature_set_path")
        if features is not None:
            feature_path = _handle(features).path
        if feature_path:
            bundle = build_dataset_from_feature_set(
                dataset_handle.path,
                feature_path,
                segments=dataset_handle.metadata.get("segments"),
                label_horizon=int(dataset_handle.metadata.get("label_horizon") or 0),
            )
        else:
            bundle = build_dataset_from_export(dataset_handle.path, segments=dataset_handle.metadata.get("segments"))
        spec = ModelSpec(model_handle.metadata["model_type"], model_handle.metadata.get("params", {}))
        trained = train_model(bundle, spec, artifact_dir)
        summary = {"model_type": spec.model_type, "rows": int(len(bundle.dataset.prepare("train"))), "feature_names": bundle.feature_names}
        return (trained.handle(dataset_handle).to_dict(), json.dumps(summary, ensure_ascii=False))


class QlibPredict:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"trained_model": ("QLIB_TRAINED_MODEL",), "dataset": ("QLIB_DATASET",), "segment": (["train", "valid", "test"],)},
            "optional": {"features": ("QLIB_FEATURE_SET",), "control": ("QLIB_CONTROL",)},
        }

    RETURN_TYPES = ("QLIB_SIGNAL_TABLE",)
    RETURN_NAMES = ("预测信号",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Model"

    def run(self, trained_model, dataset, segment, features=None, control=None):
        values = _control_values(control)
        segment = _controlled(values, "segment", segment)
        model_handle, dataset_handle = _handle(trained_model), _handle(dataset)
        feature_path = dataset_handle.metadata.get("feature_set_path")
        if features is not None:
            feature_path = _handle(features).path
        if feature_path:
            bundle = build_dataset_from_feature_set(
                dataset_handle.path,
                feature_path,
                segments=dataset_handle.metadata.get("segments"),
                label_horizon=int(dataset_handle.metadata.get("label_horizon") or 0),
            )
        else:
            bundle = build_dataset_from_export(dataset_handle.path, segments=dataset_handle.metadata.get("segments"))
        signal = predict_model(load_model(model_handle), bundle, segment)
        target = Path(model_handle.path) / f"signal_{segment}.parquet"
        signal.to_parquet(target, index=False)
        return (Handle("QLIB_SIGNAL_TABLE", str(target), metadata={"rows": len(signal), "dataset_path": dataset_handle.path}).to_dict(),)


class QlibBacktest:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"signal": ("QLIB_SIGNAL_TABLE",), "topk": ("INT", {"default": 1, "min": 1}), "n_drop": ("INT", {"default": 0, "min": 0}), "transaction_cost_bps": ("FLOAT", {"default": 5.0, "min": 0.0})},
            "optional": {"control": ("QLIB_CONTROL",)},
        }

    RETURN_TYPES = ("QLIB_BACKTEST_RESULT", "STRING")
    RETURN_NAMES = ("回测结果", "指标摘要")
    FUNCTION = "run"
    CATEGORY = "TY Quant/Backtest"

    def run(self, signal, topk=1, n_drop=0, transaction_cost_bps=5.0, control=None):
        values = _control_values(control)
        topk = _controlled(values, "topk", topk)
        n_drop = _controlled(values, "n_drop", n_drop)
        transaction_cost_bps = _controlled(values, "transaction_cost_bps", transaction_cost_bps)
        signal_handle = _handle(signal)
        table = pd.read_parquet(signal_handle.path)
        result = backtest(table, topk=int(topk), n_drop=int(n_drop), transaction_cost_bps=float(transaction_cost_bps))
        target = Path(signal_handle.path).parent / "backtest"
        target.mkdir(parents=True, exist_ok=True)
        result.equity.to_csv(target / "equity.csv", index=False)
        (target / "metrics.json").write_text(json.dumps(result.metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        result.signal.to_parquet(target / "signal.parquet", index=False)
        return (Handle("QLIB_BACKTEST_RESULT", str(target), metadata=result.metrics).to_dict(), json.dumps(result.metrics, ensure_ascii=False))


class QlibReport:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"backtest_result": ("QLIB_BACKTEST_RESULT",), "output_dir": ("STRING", {"default": "outputs/ty_quant/report"})},
            "optional": {"control": ("QLIB_CONTROL",)},
        }

    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("摘要", "权益曲线", "状态")
    OUTPUT_NODE = True
    FUNCTION = "run"
    CATEGORY = "TY Quant/Report"

    def run(self, backtest_result, output_dir, control=None):
        values = _control_values(control)
        output_dir = _controlled(values, "report_dir", output_dir)
        handle = _handle(backtest_result)
        metrics = json.loads((Path(handle.path) / "metrics.json").read_text(encoding="utf-8"))
        equity = pd.read_csv(Path(handle.path) / "equity.csv")
        result = BacktestResult(metrics, equity, pd.DataFrame())
        artifact = create_report(result, output_dir)
        return (json.dumps(artifact.summary, ensure_ascii=False), image_to_tensor(artifact.image_path), "TY Quant 回测报告已生成")


# 兼容早期节点名称
TYQuantAdjustPrices = AdjustPrices
TYQuantTrain = QlibTrain
TYQuantBacktest = QlibBacktest
TYQuantReport = QlibReport

NODE_CLASS_MAPPINGS = {
    "QlibControl": QlibControl,
    "QlibRuntime": QlibRuntime,
    "TushareConfig": TushareConfig,
    "TushareDailyFetch": TushareDailyFetch,
    "TushareToQlib": TushareToQlib,
    "TYFactorCompute": TYFactorCompute,
    "AdjustPrices": AdjustPrices,
    "QlibExport": QlibExport,
    "QlibDataset": QlibDataset,
    "QlibModel": QlibModel,
    "QlibTrain": QlibTrain,
    "QlibPredict": QlibPredict,
    "QlibBacktest": QlibBacktest,
    "QlibReport": QlibReport,
}
NODE_DISPLAY_NAME_MAPPINGS = {key: key for key in NODE_CLASS_MAPPINGS}
