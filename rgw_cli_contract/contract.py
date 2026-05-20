from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

NoArgsMode = Literal["help", "dispatch"]
ConfigPathFactory = Callable[[], Path]


@dataclass(frozen=True, slots=True)
class AppSpec:
    app_name: str
    version: str
    help_text: str
    install_script_path: Path
    no_args_mode: NoArgsMode = "help"
    config_path_factory: ConfigPathFactory | None = None
    config_bootstrap_text: str = "{}\n"
