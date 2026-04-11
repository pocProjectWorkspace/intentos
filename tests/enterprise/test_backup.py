"""Tests for core.enterprise.backup — BackupManager."""

from __future__ import annotations

import json
import os
import sys
import tarfile
import time
from pathlib import Path

import pytest

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _project_root)

from core.enterprise.backup import BackupManager


@pytest.fixture
def base(tmp_path):
    """Create a temporary ~/.intentos with some test data."""
    base = tmp_path / ".intentos"
    base.mkdir()

    # Create some test files
    (base / "config.json").write_text('{"privacy_mode": "local"}')
    logs = base / "logs"
    logs.mkdir()
    (logs / "audit.jsonl").write_text('{"event": "test"}\n')

    # Create cache dir (should be excluded)
    cache = base / "cache"
    cache.mkdir()
    (cache / "temp.dat").write_bytes(b"cached data")

    return base


def test_create_backup(base, tmp_path):
    """create_backup produces a tar.gz file in the output directory."""
    mgr = BackupManager(base_path=base)
    output_dir = tmp_path / "out"
    path = mgr.create_backup(output_dir=output_dir)

    assert os.path.exists(path)
    assert path.endswith(".tar.gz")
    assert "intentos_backup_" in path

    # Verify contents — cache should be excluded
    with tarfile.open(path, "r:gz") as tar:
        names = tar.getnames()
        assert "config.json" in names
        assert "logs/audit.jsonl" in names or "logs" in names
        # cache should not be present
        assert not any("cache" in n for n in names)


def test_restore_backup(base, tmp_path):
    """Restore overwrites current data with backup contents."""
    mgr = BackupManager(base_path=base)
    output_dir = tmp_path / "out"
    backup_path = mgr.create_backup(output_dir=output_dir)

    # Modify data
    (base / "config.json").write_text('{"privacy_mode": "cloud"}')

    # Restore
    result = mgr.restore_backup(backup_path)
    assert result is True

    # Verify original data restored
    data = json.loads((base / "config.json").read_text())
    assert data["privacy_mode"] == "local"


def test_list_backups(base, tmp_path):
    """list_backups returns entries sorted by date (newest first)."""
    mgr = BackupManager(base_path=base)
    output_dir = base / "backups"

    mgr.create_backup(output_dir=output_dir)
    time.sleep(1.1)  # ensure different second-level timestamps
    mgr.create_backup(output_dir=output_dir)

    backups = mgr.list_backups()
    assert len(backups) >= 2
    assert "filename" in backups[0]
    assert "size_mb" in backups[0]
    assert "created_at" in backups[0]


def test_data_summary(base):
    """get_data_summary returns component sizes."""
    mgr = BackupManager(base_path=base)
    summary = mgr.get_data_summary()

    assert "total_size_mb" in summary
    assert "components" in summary
    assert "logs" in summary["components"]


def test_path_traversal_blocked(base, tmp_path):
    """Backup with path traversal members raises ValueError."""
    # Create a malicious tar
    evil_tar = tmp_path / "evil.tar.gz"
    with tarfile.open(evil_tar, "w:gz") as tar:
        import io
        data = b"malicious"
        info = tarfile.TarInfo(name="../../../etc/passwd")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    mgr = BackupManager(base_path=base)
    with pytest.raises(ValueError, match="Unsafe path"):
        mgr.restore_backup(str(evil_tar))
