from __future__ import annotations

from collections.abc import Callable, Sequence

from .contract import AppSpec
from .editor import open_config_in_editor
from .helptext import print_help_text
from .installer_bridge import upgrade_via_installer


def run_app(
    spec: AppSpec,
    argv: Sequence[str],
    dispatch: Callable[[list[str]], int],
) -> int:
    args = list(argv)
    if not args and spec.no_args_mode == "help":
        print_help_text(spec.help_text)
        return 0
    if args == ["-h"]:
        print_help_text(spec.help_text)
        return 0
    if args == ["-v"]:
        print(spec.version)
        return 0
    if args == ["-u"]:
        return upgrade_via_installer(spec)
    if args == ["conf"] and spec.config_path_factory is not None:
        return open_config_in_editor(
            spec.config_path_factory,
            bootstrap_text=spec.config_bootstrap_text,
        )
    return dispatch(args)
