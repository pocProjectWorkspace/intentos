#!/usr/bin/env python3
"""Build the IntentOS backend sidecar binary for Tauri.

Runs PyInstaller to create a single-file executable, then renames it
with the target triple that Tauri expects.

Usage:
    python scripts/build-sidecar.py                    # auto-detect platform
    python scripts/build-sidecar.py --target aarch64-apple-darwin
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_FILE = os.path.join(PROJECT_ROOT, "scripts", "intentos-backend.spec")
BINARIES_DIR = os.path.join(PROJECT_ROOT, "ui", "desktop", "src-tauri", "binaries")


def detect_target_triple() -> str:
    """Detect the Rust-style target triple for the current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        arch = "aarch64" if machine == "arm64" else "x86_64"
        return f"{arch}-apple-darwin"
    elif system == "windows":
        arch = "x86_64" if machine in ("amd64", "x86_64") else machine
        return f"{arch}-pc-windows-msvc"
    elif system == "linux":
        arch = "x86_64" if machine == "x86_64" else machine
        return f"{arch}-unknown-linux-gnu"
    else:
        return f"{machine}-unknown-{system}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build IntentOS sidecar binary")
    parser.add_argument("--target", default=None,
                        help="Target triple (auto-detected if omitted)")
    args = parser.parse_args()

    target = args.target or detect_target_triple()
    is_windows = "windows" in target

    print(f"  Building sidecar for target: {target}")
    print(f"  Spec file: {SPEC_FILE}")
    print(f"  Output dir: {BINARIES_DIR}")
    print()

    # Ensure output directory exists
    os.makedirs(BINARIES_DIR, exist_ok=True)

    # Check PyInstaller is available
    if not shutil.which("pyinstaller"):
        print("  [!!] PyInstaller not found. Install with: pip install pyinstaller")
        sys.exit(1)

    # Run PyInstaller
    dist_dir = os.path.join(PROJECT_ROOT, "build", "sidecar-dist")
    work_dir = os.path.join(PROJECT_ROOT, "build", "sidecar-work")

    cmd = [
        "pyinstaller",
        SPEC_FILE,
        "--distpath", dist_dir,
        "--workpath", work_dir,
        "--noconfirm",
    ]

    print(f"  [..] Running PyInstaller...")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("  [!!] PyInstaller failed")
        sys.exit(1)

    # Rename binary with target triple
    src_name = "intentos-backend.exe" if is_windows else "intentos-backend"
    src_path = os.path.join(dist_dir, src_name)

    dst_name = f"intentos-backend-{target}"
    if is_windows:
        dst_name += ".exe"
    dst_path = os.path.join(BINARIES_DIR, dst_name)

    if not os.path.exists(src_path):
        print(f"  [!!] Built binary not found at {src_path}")
        sys.exit(1)

    shutil.copy2(src_path, dst_path)
    size_mb = os.path.getsize(dst_path) / (1024 * 1024)
    print(f"  [ok] Sidecar ready: {dst_name} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
