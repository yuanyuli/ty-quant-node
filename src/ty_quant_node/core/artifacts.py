"""可复现产物的原子写入和目录发布工具。"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import tempfile
from collections.abc import Iterator


class ArtifactConflictError(RuntimeError):
    """目标产物已存在，避免覆盖已有版本。"""


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
