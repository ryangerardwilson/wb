from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .contract import AppSpec
from .versioning import is_newer_version, normalize_version


def resolve_install_script_path(anchor_file: str | Path) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "install.sh"
    return Path(anchor_file).resolve().with_name("install.sh")


def _missing_installer_error(path: Path) -> int:
    print(f"install.sh is missing: {path}", file=sys.stderr)
    return 1


def read_installer_latest_version(install_script_path: Path) -> str | None:
    if not install_script_path.exists():
        return None
    result = subprocess.run(
        ["bash", str(install_script_path), "-v"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    return normalize_version(lines[-1])


def run_install_script(install_script_path: Path, *args: str) -> int:
    if not install_script_path.exists():
        return _missing_installer_error(install_script_path)
    return subprocess.run(["bash", str(install_script_path), *args], check=False).returncode


def upgrade_via_installer(spec: AppSpec) -> int:
    install_script_path = spec.install_script_path
    if not install_script_path.exists():
        return _missing_installer_error(install_script_path)

    latest = read_installer_latest_version(install_script_path)
    current = normalize_version(spec.version)
    if latest and current and current != "0.0.0" and not is_newer_version(latest, current):
        print(f"Already running the latest version ({spec.version}).")
        return 0

    if latest:
        if current and current != "0.0.0":
            print(f"Upgrading from {spec.version} to {latest}…")
        else:
            print(f"Upgrading to {latest}…")

    return run_install_script(install_script_path, "-u")
