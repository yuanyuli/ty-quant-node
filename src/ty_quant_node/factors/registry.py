"""版本化因子定义和 Alpha158 benchmark 适配。"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any

import yaml


_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class FactorSpec:
    name: str
    version: str
    expression: str
    inputs: tuple[str, ...]
    lookback: int
    adjustment_policy: str = "point_in_time"
    null_policy: str = "drop"
    category: str = "custom"


def _parse(payload: Any, source: Path) -> FactorSpec:
    if not isinstance(payload, dict):
        raise ValueError(f"因子定义必须是对象: {source}")
    required = {"name", "version", "expression", "inputs", "lookback"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"因子定义缺少字段: {', '.join(sorted(missing))}: {source}")
    name = str(payload["name"]).strip()
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"因子名称无效: {name}")
    expression = str(payload["expression"]).strip()
    if not expression or any(token in expression.lower() for token in ("__", "import", "exec(", "eval(", "open(")):
        raise ValueError(f"因子表达式不安全: {name}")
    inputs = payload["inputs"]
    if not isinstance(inputs, list) or not all(isinstance(item, str) and item.strip() for item in inputs):
        raise ValueError(f"因子 inputs 必须是非空字符串数组: {name}")
    try:
        lookback = int(payload["lookback"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"因子 lookback 必须是非负整数: {name}") from exc
    if lookback < 0:
        raise ValueError(f"因子 lookback 必须是非负整数: {name}")
    return FactorSpec(
        name=name,
        version=str(payload["version"]),
        expression=expression,
        inputs=tuple(item.strip().lstrip("$") for item in inputs),
        lookback=lookback,
        adjustment_policy=str(payload.get("adjustment_policy", "point_in_time")),
        null_policy=str(payload.get("null_policy", "drop")),
        category=str(payload.get("category", "custom")),
    )


def load_factor_specs(root: str | Path | None = None) -> list[FactorSpec]:
    root_path = Path(root) if root is not None else Path(__file__).with_name("builtin")
    if not root_path.exists():
        raise ValueError(f"因子目录不存在: {root_path}")
    specs = []
    for path in sorted(root_path.rglob("*.yaml")):
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if document is not None:
                specs.append(_parse(document, path))
    names: set[str] = set()
    for spec in specs:
        if spec.name in names:
            raise ValueError(f"因子名称重复: {spec.name}")
        names.add(spec.name)
    return specs


def load_alpha158_specs() -> list[FactorSpec]:
    try:
        from qlib.contrib.data.loader import Alpha158DL
    except ModuleNotFoundError as exc:
        raise RuntimeError("当前 Python 环境没有安装 Qlib，无法加载 Alpha158") from exc
    fields, names = Alpha158DL.get_feature_config()
    return [
        FactorSpec(
            name=str(name),
            version="qlib",
            expression=str(expression),
            inputs=tuple(sorted(set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", str(expression))))),
            lookback=60,
            adjustment_policy="qlib_adjusted_provider",
            null_policy="drop",
            category="alpha158",
        )
        for expression, name in zip(fields, names)
    ]
