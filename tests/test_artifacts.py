from pathlib import Path

import pytest

from ty_quant_node.core.artifacts import (
    ArtifactConflictError,
    atomic_file,
    artifact_transaction,
    atomic_write_text,
)


def test_artifact_transaction_publishes_complete_directory(tmp_path):
    target = tmp_path / "snapshot"

    with artifact_transaction(target) as staging:
        (staging / "raw.parquet").write_bytes(b"raw")
        (staging / "manifest.json").write_text('{"complete": true}', encoding="utf-8")

    assert target.is_dir()
    assert sorted(path.name for path in target.iterdir()) == ["manifest.json", "raw.parquet"]
    assert not list(tmp_path.glob(".snapshot.*"))


def test_artifact_transaction_cleans_staging_after_failure(tmp_path):
    target = tmp_path / "provider"

    with pytest.raises(RuntimeError, match="boom"):
        with artifact_transaction(target) as staging:
            (staging / "manifest.json").write_text("partial", encoding="utf-8")
            raise RuntimeError("boom")

    assert not target.exists()
    assert not list(tmp_path.glob(".provider.*"))


def test_artifact_transaction_rejects_existing_target(tmp_path):
    target = tmp_path / "features"
    target.mkdir()

    with pytest.raises(ArtifactConflictError, match="已存在"):
        with artifact_transaction(target):
            pass


def test_atomic_write_text_replaces_file_without_tmp_leftovers(tmp_path):
    target = tmp_path / "manifest.json"
    atomic_write_text(target, '{"version": 1}')
    atomic_write_text(target, '{"version": 2}')

    assert target.read_text(encoding="utf-8") == '{"version": 2}'
    assert not [path for path in tmp_path.iterdir() if path.name.startswith(".manifest.json.")]


def test_atomic_file_cleans_temp_when_writer_fails(tmp_path):
    target = tmp_path / "signal.parquet"

    with pytest.raises(RuntimeError, match="write failed"):
        with atomic_file(target) as staging:
            staging.write_bytes(b"partial")
            raise RuntimeError("write failed")

    assert not target.exists()
    assert not list(tmp_path.glob(".signal.parquet.*"))
