"""IntentOS Backup & Restore — export/import ~/.intentos data."""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import time
from pathlib import Path
from typing import Optional


class BackupManager:
    """Backup and restore the IntentOS data directory."""

    def __init__(self, base_path: Optional[Path] = None):
        self._base = base_path or Path.home() / ".intentos"

    def create_backup(self, output_dir: Optional[Path] = None) -> str:
        """Create a .tar.gz backup of ~/.intentos (excluding cache and temp).

        Returns the path to the backup file.
        """
        output_dir = output_dir or self._base / "backups"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"intentos_backup_{timestamp}.tar.gz"
        backup_path = output_dir / backup_name

        with tarfile.open(backup_path, "w:gz") as tar:
            for item in sorted(self._base.iterdir()):
                # Skip cache, temp, backups, and the backup file itself
                if item.name in ("cache", "backups", "exports"):
                    continue
                tar.add(item, arcname=item.name)

        return str(backup_path)

    def restore_backup(self, backup_path: str) -> bool:
        """Restore from a .tar.gz backup.

        Preserves the current state by creating a pre-restore backup first.
        """
        backup_file = Path(backup_path)
        if not backup_file.exists():
            return False

        # Create a safety backup before restoring
        self.create_backup()

        # Extract (overwriting existing files)
        with tarfile.open(backup_file, "r:gz") as tar:
            # Security: check for path traversal
            for member in tar.getmembers():
                if member.name.startswith("/") or ".." in member.name:
                    raise ValueError(f"Unsafe path in backup: {member.name}")
            tar.extractall(path=self._base)

        return True

    def list_backups(self) -> list:
        """List available backups."""
        backup_dir = self._base / "backups"
        if not backup_dir.exists():
            return []
        backups = []
        for f in sorted(backup_dir.glob("intentos_backup_*.tar.gz"), reverse=True):
            stat = f.stat()
            backups.append({
                "filename": f.name,
                "path": str(f),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)
                ),
            })
        return backups

    def get_data_summary(self) -> dict:
        """Return a summary of what's in ~/.intentos."""
        summary: dict = {"total_size_mb": 0.0, "components": {}}
        if not self._base.exists():
            return summary

        total = 0
        for item in sorted(self._base.iterdir()):
            if item.is_dir():
                size = sum(
                    f.stat().st_size for f in item.rglob("*") if f.is_file()
                )
            elif item.is_file():
                size = item.stat().st_size
            else:
                continue
            summary["components"][item.name] = round(size / (1024 * 1024), 2)
            total += size

        summary["total_size_mb"] = round(total / (1024 * 1024), 2)
        return summary
