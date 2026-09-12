"""ComfyUI 节点适配层。节点之间只传递版本化轻量句柄。"""

import json
from pathlib import Path
import pandas as pd

from .core.handles import Handle
from .data import apply_adjustment
from .data.tushare_source import TushareDailySource
from .backend.market import export_qlib, normalize_market_frame
from .backend.qlib_backend import build_dataset_from_export
from .backend.model_backend import ModelSpec, train_model, predict_model, load_model
from .backend.backtest_backend import backtest, BacktestResult
from .core.report import create_report, image_to_tensor


def _handle(value) -> Handle:
    return value if isinstance(value, Handle) else Handle.from_dict(value)


class TushareConfig:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"token_source": (["environment", "server_config"],), "retries": ("INT", {"default": 3, "min": 1, "max": 5})}}

    RETURN_TYPES = ("TUSHARE_CONFIG",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Data"

    def run(self, token_source="environment", retries=3):
        return (Handle("TUSHARE_CONFIG", "", metadata={"token_source": token_source, "retries": int(retries)}).to_dict(),)


class QlibRuntime:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"provider_uri": ("STRING", {"default": ""}), "region": (["cn", "us"],), "seed": ("INT", {"default": 42, "min": 0}), "experiment_uri": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("QLIB_RUNTIME",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Qlib"

    def run(self, provider_uri, region="cn", seed=42, experiment_uri=""):
        import random
        import numpy as np
        try:
            import qlib
        except ModuleNotFoundError as exc:
            if exc.name != "qlib":
                raise
            return (Handle("QLIB_RUNTIME", path, metadata={"region": region, "seed": int(seed), "experiment_uri": experiment_uri, "qlib_version": "unavailable", "dataset_backend": "compat"}).to_dict(),)

        path = str(Path(provider_uri).resolve()) if provider_uri else ""
        qlib.init(provider_uri=path or None, region=region, dataset_cache=None, expression_cache=None, clear_mem_cache=True)
        random.seed(int(seed))
        np.random.seed(int(seed))
        return (Handle("QLIB_RUNTIME", path, metadata={"region": region, "seed": int(seed), "experiment_uri": experiment_uri, "qlib_version": getattr(qlib, "__version__", "unknown")}).to_dict(),)


class TushareDailyFetch:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("TUSHARE_CONFIG",), "ts_codes": ("STRING", {"default": "000001.SZ"}), "start_date": ("STRING", {"default": "20240101"}), "end_date": ("STRING", {"default": "20241231"}), "output_dir": ("STRING", {"default": "outputs/ty_quant"})}}

    RETURN_TYPES = ("QLIB_EXPORT",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Data"

    def run(self, config, ts_codes, start_date, end_date, output_dir):
        cfg = _handle(config)
        source = TushareDailySource(retries=int(cfg.metadata.get("retries", 3)))
        data = source.fetch([code.strip() for code in ts_codes.split(",") if code.strip()], start_date, end_date)
        return (export_qlib(data, output_dir, adjustment="qfq").to_dict(),)


class AdjustPrices:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"csv_path": ("STRING", {"default": ""}), "adjustment": (["qfq", "hfq", "none"],), "output_path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING",)
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
        return {"required": {"csv_path": ("STRING", {"default": ""}), "adjustment": (["qfq", "hfq", "none"],), "output_dir": ("STRING", {"default": "outputs/ty_quant/provider"})}}

    RETURN_TYPES = ("QLIB_EXPORT",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Qlib"

    def run(self, csv_path, adjustment, output_dir):
        return (export_qlib(pd.read_csv(csv_path), output_dir, adjustment=adjustment).to_dict(),)


class QlibDataset:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"export": ("QLIB_EXPORT",), "train_start": ("STRING", {"default": ""}), "train_end": ("STRING", {"default": ""}), "test_start": ("STRING", {"default": ""}), "test_end": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("QLIB_DATASET",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Qlib"

    def run(self, export, train_start="", train_end="", test_start="", test_end=""):
        handle = _handle(export)
        segments = None
        if train_start and train_end and test_start and test_end:
            segments = {"train": (train_start, train_end), "test": (test_start, test_end)}
        return (build_dataset_from_export(handle.path, segments=segments).handle().to_dict(),)


class QlibModel:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model_type": (["linear", "lightgbm"],), "params_json": ("STRING", {"default": "{}"})}}

    RETURN_TYPES = ("QLIB_MODEL_SPEC",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Model"

    def run(self, model_type, params_json="{}"):
        try:
            params = json.loads(params_json or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("QlibModel 参数 JSON 无效") from exc
        return (Handle("QLIB_MODEL_SPEC", "", metadata={"model_type": ModelSpec(model_type, params).model_type, "params": params}).to_dict(),)


class QlibTrain:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"dataset": ("QLIB_DATASET",), "model": ("QLIB_MODEL_SPEC",), "artifact_dir": ("STRING", {"default": "outputs/ty_quant/model"})}}

    RETURN_TYPES = ("QLIB_TRAINED_MODEL", "STRING")
    FUNCTION = "run"
    CATEGORY = "TY Quant/Model"

    def run(self, dataset, model, artifact_dir):
        dataset_handle, model_handle = _handle(dataset), _handle(model)
        bundle = build_dataset_from_export(dataset_handle.path, segments=dataset_handle.metadata.get("segments"))
        spec = ModelSpec(model_handle.metadata["model_type"], model_handle.metadata.get("params", {}))
        trained = train_model(bundle, spec, artifact_dir)
        summary = {"model_type": spec.model_type, "rows": int(len(bundle.dataset.prepare("train"))), "feature_names": bundle.feature_names}
        return (trained.handle(dataset_handle).to_dict(), json.dumps(summary, ensure_ascii=False))


class QlibPredict:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"trained_model": ("QLIB_TRAINED_MODEL",), "dataset": ("QLIB_DATASET",), "segment": (["train", "valid", "test"],)}}

    RETURN_TYPES = ("QLIB_SIGNAL_TABLE",)
    FUNCTION = "run"
    CATEGORY = "TY Quant/Model"

    def run(self, trained_model, dataset, segment):
        model_handle, dataset_handle = _handle(trained_model), _handle(dataset)
        bundle = build_dataset_from_export(dataset_handle.path, segments=dataset_handle.metadata.get("segments"))
        signal = predict_model(load_model(model_handle), bundle, segment)
        target = Path(model_handle.path) / f"signal_{segment}.parquet"
        signal.to_parquet(target, index=False)
        return (Handle("QLIB_SIGNAL_TABLE", str(target), metadata={"rows": len(signal), "dataset_path": dataset_handle.path}).to_dict(),)


class QlibBacktest:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"signal": ("QLIB_SIGNAL_TABLE",), "topk": ("INT", {"default": 1, "min": 1}), "n_drop": ("INT", {"default": 0, "min": 0}), "transaction_cost_bps": ("FLOAT", {"default": 5.0, "min": 0.0})}}

    RETURN_TYPES = ("QLIB_BACKTEST_RESULT", "STRING")
    FUNCTION = "run"
    CATEGORY = "TY Quant/Backtest"

    def run(self, signal, topk=1, n_drop=0, transaction_cost_bps=5.0):
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
        return {"required": {"backtest_result": ("QLIB_BACKTEST_RESULT",), "output_dir": ("STRING", {"default": "outputs/ty_quant/report"})}}

    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    OUTPUT_NODE = True
    FUNCTION = "run"
    CATEGORY = "TY Quant/Report"

    def run(self, backtest_result, output_dir):
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
    "QlibRuntime": QlibRuntime,
    "TushareConfig": TushareConfig,
    "TushareDailyFetch": TushareDailyFetch,
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
