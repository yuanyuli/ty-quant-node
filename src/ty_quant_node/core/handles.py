"""ComfyUI 工作流中传递的轻量句柄。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar


@dataclass(frozen=True)
class Handle:
    kind: str
    path: str
    version: str = "1"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    KNOWN_KINDS: ClassVar[frozenset[str]] = frozenset(
        {
            "QLIB_RUNTIME",
            "TUSHARE_CONFIG",
            "MARKET_DATA",
            "QLIB_EXPORT",
            "QLIB_DATASET",
            "QLIB_MODEL_SPEC",
            "QLIB_TRAINED_MODEL",
            "QLIB_SIGNAL_TABLE",
            "QLIB_BACKTEST_RESULT",
            "QLIB_REPORT",
        }
    )

    def __post_init__(self) -> None:
        if self.kind not in self.KNOWN_KINDS:
            raise ValueError(f"未知句柄类型: {self.kind}")
        if not self.version:
            raise ValueError("句柄版本不能为空")
        if not isinstance(self.metadata, dict):
            raise TypeError("句柄 metadata 必须是对象")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "version": self.version,
            "path": self.path,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Handle":
        if not isinstance(payload, dict):
            raise TypeError("句柄必须是对象")
        missing = {"kind", "version", "path"} - payload.keys()
        if missing:
            raise ValueError(f"句柄缺少字段: {', '.join(sorted(missing))}")
        return cls(
            kind=str(payload["kind"]),
            version=str(payload["version"]),
            path=str(payload["path"]),
            created_at=str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
            metadata=dict(payload.get("metadata") or {}),
        )
