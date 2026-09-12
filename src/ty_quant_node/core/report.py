"""回测报告和 ComfyUI IMAGE 转换。"""

import json
from pathlib import Path
import numpy as np


def create_report(result, output_dir: str | Path):
    import matplotlib.pyplot as plt

    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    curve = result.equity
    fig, ax = plt.subplots(figsize=(8, 4), dpi=120)
    if not curve.empty:
        ax.plot(curve["datetime"], curve["equity"], color="#1f6feb", linewidth=2)
    ax.set_title("TY Quant Backtest Equity")
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    image_path = out / "equity.png"
    fig.savefig(image_path, format="png")
    plt.close(fig)
    summary = dict(result.metrics)
    summary["days"] = int(len(curve))
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return type("ReportArtifact", (), {"image_path": image_path, "summary": summary, "output_dir": out})()


def image_to_tensor(image_path: str | Path):
    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    array = np.asarray(image, dtype=np.float32) / 255.0
    tensor = array[None, ...]
    try:
        import torch

        return torch.from_numpy(tensor)
    except ImportError:
        return tensor
