"""本地路径白名单校验。"""

from pathlib import Path
from urllib.parse import urlsplit
import os
import re


def resolve_allowed_path(path: str | os.PathLike[str], roots: list[str | os.PathLike[str]], *, must_exist=False) -> Path:
    raw = str(path)
    if not raw.strip():
        raise ValueError("路径不能为空")
    parsed = urlsplit(raw)
    is_windows_drive = bool(re.match(r"^[A-Za-z]:[\\/]", raw))
    if (parsed.scheme and not is_windows_drive) or raw.startswith(("\\\\?\\", "\\\\.\\")):
        raise ValueError("只允许本地文件路径")
    parts = Path(raw).parts
    if ".." in parts:
        raise ValueError("路径穿越被拒绝")
    root_paths = [Path(root).expanduser().resolve() for root in roots]
    if not root_paths:
        raise ValueError("必须提供路径白名单")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root_paths[0] / candidate
    candidate = candidate.resolve()
    candidate_key = os.path.normcase(str(candidate))
    for root in root_paths:
        root_key = os.path.normcase(str(root))
        try:
            if os.path.commonpath([candidate_key, root_key]) == root_key:
                if must_exist and not candidate.exists():
                    raise ValueError(f"路径不存在: {candidate}")
                return candidate
        except ValueError:
            continue
    raise ValueError(f"路径不在白名单内: {candidate}")
