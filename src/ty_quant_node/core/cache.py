"""确定性缓存键和缓存路径。"""

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(config: dict[str, Any], input_hashes: dict[str, str], versions: dict[str, str]) -> str:
    payload = {"config": config, "input_hashes": input_hashes, "versions": versions}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ArtifactCache:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str, suffix: str = "") -> Path:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("缓存键格式无效")
        path = self.root / f"{key}{suffix}"
        if path.parent != self.root:
            raise ValueError("缓存路径越界")
        return path

    def valid(self, key: str, suffix: str = "") -> bool:
        return self.path_for(key, suffix).exists()
