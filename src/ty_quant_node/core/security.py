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


def configured_allowed_roots() -> list[Path]:
    """返回节点运行时的本地路径白名单。"""

    roots: list[Path] = [Path.cwd()]
    package_root = Path(__file__).resolve().parents[3]
    if package_root.exists():
        roots.append(package_root)
    configured = os.getenv("TY_QUANT_ALLOWED_ROOTS", "")
    if configured:
        roots.extend(Path(item).expanduser() for item in configured.split(os.pathsep) if item.strip())
    try:
        import folder_paths
    except (ImportError, AttributeError, OSError):
        folder_paths = None
    if folder_paths is not None:
        for name in ("base_path", "input_directory", "output_directory", "temp_directory"):
            value = getattr(folder_paths, name, None)
            if value:
                roots.append(Path(value))
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        resolved = root.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            unique.append(resolved)
            seen.add(key)
    return unique


def resolve_node_path(path: str | os.PathLike[str], *, must_exist: bool = False) -> Path:
    """按节点运行时白名单解析路径并拒绝 URL、设备路径和穿越。"""

    return resolve_allowed_path(path, configured_allowed_roots(), must_exist=must_exist)
