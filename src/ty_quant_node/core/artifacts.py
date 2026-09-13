"""可复现产物的原子写入和目录发布工具。"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
from collections.abc import Iterator


class ArtifactConflictError(RuntimeError):
    """目标产物已存在，避免覆盖已有版本。"""


class ArtifactIntegrityError(ValueError):
    """产物文件与 manifest 声明不一致。"""


def sha256_file(path: str | os.PathLike[str]) -> str:
    """计算已提交或 staging 文件的 SHA-256。"""

    digest = hashlib.sha256()
    with _resolved(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest_file(
    root: str | os.PathLike[str],
    manifest: dict,
    key: str,
    *,
    relative_path: str | os.PathLike[str] | None = None,
) -> Path:
    """只读校验 manifest 中声明的单个文件并返回其绝对路径。"""

    if not isinstance(manifest, dict):
        raise ArtifactIntegrityError("artifact manifest 必须是对象，无法校验 hash")
    files = manifest.get("files")
    expected = files.get(key) if isinstance(files, dict) else None
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ArtifactIntegrityError(f"artifact manifest 缺少有效的 {key} hash")
    relative = Path(relative_path if relative_path is not None else key)
    if relative.is_absolute() or ".." in relative.parts:
        raise ArtifactIntegrityError(f"artifact manifest 文件路径非法，拒绝校验 hash: {relative}")
    base = _resolved(root)
    target = (base / relative).resolve()
    try:
        if os.path.commonpath([os.path.normcase(str(base)), os.path.normcase(str(target))]) != os.path.normcase(str(base)):
            raise ArtifactIntegrityError(f"artifact manifest 文件路径越界，拒绝校验 hash: {relative}")
    except ValueError as exc:
        raise ArtifactIntegrityError(f"artifact manifest 文件路径越界，拒绝校验 hash: {relative}") from exc
    if not target.is_file():
        raise ArtifactIntegrityError(f"artifact 文件不存在，无法校验 hash: {target}")
    actual = sha256_file(target)
    if actual.lower() != expected.lower():
        raise ArtifactIntegrityError(f"artifact 文件 hash 不匹配: {target}")
    return target


def _resolved(path: str | os.PathLike[str]) -> Path:
    value = Path(path).expanduser().resolve()
    if not str(value).strip():
        raise ValueError("artifact 路径不能为空")
    return value


@contextmanager
def artifact_transaction(target: str | os.PathLike[str]) -> Iterator[Path]:
    """在目标同级目录构建产物，退出上下文时一次性发布。"""

    final_path = _resolved(target)
    if final_path.exists():
        raise ArtifactConflictError(f"artifact 目标已存在: {final_path}")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = Path(tempfile.mkdtemp(prefix=f".{final_path.name}.", dir=str(final_path.parent)))
    try:
        yield staging_path
        if final_path.exists():
            raise ArtifactConflictError(f"artifact 目标在提交前已存在: {final_path}")
        os.replace(str(staging_path), str(final_path))
    except BaseException:
        shutil.rmtree(staging_path, ignore_errors=True)
        raise


@contextmanager
def atomic_file(target: str | os.PathLike[str]) -> Iterator[Path]:
    """在目标文件同级目录生成临时文件，退出时原子替换。"""

    final_path = _resolved(target)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{final_path.name}.",
            suffix=".tmp",
            dir=str(final_path.parent),
            delete=False,
        ) as stream:
            temp_name = stream.name
        yield Path(temp_name)
        os.replace(temp_name, final_path)
    except BaseException:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise


def atomic_write_bytes(target: str | os.PathLike[str], content: bytes) -> Path:
    """通过同目录临时文件替换单个文件。"""

    with atomic_file(target) as staging:
        staging.write_bytes(content)
        with staging.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
    return _resolved(target)


def atomic_write_text(
    target: str | os.PathLike[str],
    content: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    return atomic_write_bytes(target, content.encode(encoding))
