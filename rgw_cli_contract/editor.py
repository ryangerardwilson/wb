from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Callable


def resolve_editor_command() -> list[str]:
    editor = (os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim").strip()
    command = shlex.split(editor) if editor else ["vim"]
    return command or ["vim"]


def open_path_in_editor(path: Path) -> int:
    return subprocess.run([*resolve_editor_command(), str(path)], check=False).returncode


def open_config_in_editor(
    path_factory: Callable[[], Path],
    *,
    bootstrap_text: str = "{}\n",
) -> int:
    config_path = path_factory()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(bootstrap_text, encoding="utf-8")
    return open_path_in_editor(config_path)
