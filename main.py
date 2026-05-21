#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _version import __version__
from rgw_cli_contract import AppSpec, resolve_install_script_path, run_app


APP_NAME = "wb"
DEFAULT_STRUCTURE_NAME = "structure.json"
DRAFT_MARKER = "<!-- wb:draft:start -->"
VIM_WRAP_MODELINE = "<!-- wb: vim wraps prose at 79 columns -->"
SHORT_VIM_WRAP_MODELINE = "<!-- vim: setlocal tw=79 cc=79 wrap lbr fo+=t: -->"
OLD_VIM_WRAP_MODELINE = "<!-- vim: setlocal textwidth=79 colorcolumn=79 wrap linebreak formatoptions+=t: -->"
SCAFFOLD_WIDTH = 79

HELP_TEXT = """Writer's Block
write long work one proposition at a time

flags:
  wb -h
    show this help
  wb -v
    print the installed version
  wb -u
    upgrade to the latest release

features:
  create a generic book structure file
  # init [structure_json]
  wb init
  wb init ./structure.json

  save or edit a named preset
  # preset <name> <structure_json> <drafts_dir>
  wb preset "an eye for an eye" ./structure.json ./drafts
  wb conf

  open the next unfinished proposition in your editor
  # <structure_json> <drafts_dir> [-1]
  wb ./structure.json ./drafts
  wb ./structure.json ./drafts -1

  use a named preset
  # <preset> [status|ls|show|export]
  wb "an eye for an eye"
  wb "an eye for an eye" status

  inspect the active book without opening the editor
  # <structure_json> <drafts_dir> status|ls|show
  wb ./structure.json ./drafts status
  wb ./structure.json ./drafts ls
  wb ./structure.json ./drafts show

  export completed draft bodies into a manuscript
  # <structure_json> <drafts_dir> export [-all] [-o <output_md>]
  wb ./structure.json ./drafts export -o manuscript.md
  wb "an eye for an eye" export -all
"""

APP_CONFIG_BOOTSTRAP = """{
  "extension": "md",
  "min_chars": 500,
  "presets": {}
}
"""

BOOK_STRUCTURE_BOOTSTRAP = """{
  "title": "Untitled Book",
  "settings": {
    "extension": "md",
    "min_chars": 500
  },
  "chapters": [
    {
      "title": "Chapter One",
      "propositions": [
        "State the first proposition this chapter needs to prove."
      ]
    }
  ]
}
"""

TARGET_COMMANDS = {
    "w": "write",
    "write": "write",
    "st": "status",
    "status": "status",
    "ls": "list",
    "list": "list",
    "sh": "show",
    "show": "show",
    "x": "export",
    "export": "export",
}


@dataclass(frozen=True)
class BookTarget:
    structure_path: Path
    drafts_dir: Path
    preset_name: str | None = None


@dataclass(frozen=True)
class WorkItem:
    chapter_index: int
    proposition_index: int
    chapter_title: str
    proposition: str
    path: Path
    min_chars: int


def xdg_config_home() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".config"


def app_config_path() -> Path:
    return xdg_config_home() / APP_NAME / "config.json"


def app_defaults() -> dict[str, Any]:
    return {
        "extension": "md",
        "min_chars": 500,
        "presets": {},
    }


def load_app_config() -> dict[str, Any]:
    path = app_config_path()
    if not path.exists():
        return app_defaults()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"invalid app config: {exc}")
    if not isinstance(raw, dict):
        die("app config must be a JSON object")

    config = app_defaults()
    config.update(raw)
    if not isinstance(config.get("presets"), dict):
        die("app config presets must be a JSON object")
    return config


def write_app_config(config: dict[str, Any]) -> None:
    path = app_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def muted_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def die(message: str, code: int = 2) -> None:
    print(f"wb: {message}", file=sys.stderr)
    raise SystemExit(code)


def resolve_path(value: str, base: Path) -> Path:
    if not value.strip():
        die("path must not be empty")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def resolve_arg_path(value: str) -> Path:
    return resolve_path(value, Path.cwd())


def resolve_preset(name: str) -> BookTarget:
    config = load_app_config()
    presets = config.get("presets", {})
    if not isinstance(presets, dict):
        die("app config presets must be a JSON object")

    raw = presets.get(name)
    if raw is None:
        die(
            f"unknown preset: {name}\n"
            "run wb preset <name> <structure_json> <drafts_dir> or wb conf"
        )
    if not isinstance(raw, dict):
        die(f"preset {name!r} must be a JSON object")

    structure = raw.get("structure")
    drafts = raw.get("drafts")
    if not isinstance(structure, str) or not structure.strip():
        die(f"preset {name!r} requires a structure path")
    if not isinstance(drafts, str) or not drafts.strip():
        die(f"preset {name!r} requires a drafts dir")

    base = app_config_path().parent
    return BookTarget(
        structure_path=resolve_path(structure, base),
        drafts_dir=resolve_path(drafts, base),
        preset_name=name,
    )


def parse_target(argv: list[str]) -> tuple[BookTarget, str, list[str]]:
    if not argv:
        die("valid shape: wb <structure_json> <drafts_dir> [status|ls|show|export]")

    if len(argv) >= 2 and argv[1] not in TARGET_COMMANDS:
        target = BookTarget(
            structure_path=resolve_arg_path(argv[0]),
            drafts_dir=resolve_arg_path(argv[1]),
        )
        rest = argv[2:]
    else:
        target = resolve_preset(argv[0])
        rest = argv[1:]

    if not rest or rest[0].startswith("-"):
        return target, "write", rest

    command = TARGET_COMMANDS.get(rest[0])
    if command is None:
        die(f"unknown command: {rest[0]}")
    return target, command, rest[1:]


def load_structure(path: Path) -> dict[str, Any]:
    try:
        structure = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"structure not found: {path}\nrun wb init <structure_json>")
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")

    if not isinstance(structure, dict):
        die("structure root must be a JSON object")
    if not isinstance(structure.get("chapters"), list) or not structure["chapters"]:
        die("structure must contain a non-empty chapters array")
    return structure


def structure_settings(structure: dict[str, Any]) -> dict[str, Any]:
    raw = structure.get("settings", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        die("structure settings must be an object")

    config = load_app_config()
    merged = {
        "extension": config.get("extension", "md"),
        "min_chars": config.get("min_chars", 500),
    }
    for key, value in raw.items():
        merged[key] = value
    return merged


def min_chars_for(structure: dict[str, Any], chapter: dict[str, Any]) -> int:
    value = chapter.get("min_chars", structure_settings(structure).get("min_chars", 500))
    try:
        return int(value)
    except (TypeError, ValueError):
        die(f"invalid min_chars value: {value!r}")


def work_items(target: BookTarget, structure: dict[str, Any]) -> list[WorkItem]:
    items: list[WorkItem] = []
    root = target.drafts_dir
    extension = str(structure_settings(structure).get("extension", "md")).lstrip(".") or "md"

    for chapter_index, chapter in enumerate(structure["chapters"]):
        if not isinstance(chapter, dict):
            die(f"chapter {chapter_index + 1} must be an object")

        title = str(chapter.get("title", f"Chapter {chapter_index + 1}"))
        propositions = chapter.get("propositions")
        if not isinstance(propositions, list) or not propositions:
            die(f"{title}: propositions must be a non-empty array")

        chapter_dir = root / f"{chapter_index:02d}-{slugify(title)}"
        chapter_min_chars = min_chars_for(structure, chapter)

        for proposition_index, proposition in enumerate(propositions, start=1):
            text = str(proposition).strip()
            if not text:
                die(f"{title}: empty proposition {proposition_index}")
            items.append(
                WorkItem(
                    chapter_index=chapter_index,
                    proposition_index=proposition_index,
                    chapter_title=title,
                    proposition=text,
                    path=chapter_dir / f"{proposition_index:02d}.{extension}",
                    min_chars=chapter_min_chars,
                )
            )

    return items


def draft_body(path: Path) -> str:
    if not path.exists():
        return ""

    content = path.read_text(encoding="utf-8")
    if DRAFT_MARKER not in content:
        return content.strip()
    body = content.split(DRAFT_MARKER, 1)[1]
    body = body.replace(VIM_WRAP_MODELINE, "")
    body = body.replace(SHORT_VIM_WRAP_MODELINE, "")
    body = body.replace(OLD_VIM_WRAP_MODELINE, "")
    return body.strip()


def char_count(path: Path) -> int:
    return len(draft_body(path))


def item_complete(item: WorkItem) -> bool:
    return char_count(item.path) >= item.min_chars


def draft_scaffold(item: WorkItem, total_props: int) -> str:
    wrapped = "\n".join(
        f"> {line}" if line else ">"
        for line in textwrap.wrap(item.proposition, width=SCAFFOLD_WIDTH - 2)
    )
    instructions = "\n".join(
        textwrap.wrap(
            "Write below this marker. The proposition text above is scaffolding "
            "and does not count.",
            width=SCAFFOLD_WIDTH,
        )
    )
    char_label = "character" if item.min_chars == 1 else "characters"
    return f"""# {item.chapter_title}

{VIM_WRAP_MODELINE}

Proposition {item.proposition_index} of {total_props}

## Proposition

{wrapped}

## Draft

{instructions}
Completion requires at least {item.min_chars} {char_label} below the marker.

{DRAFT_MARKER}
"""


def normalize_draft_scaffold(item: WorkItem, total_props: int) -> None:
    if not item.path.exists():
        return
    content = item.path.read_text(encoding="utf-8")
    if DRAFT_MARKER not in content:
        return
    body = content.split(DRAFT_MARKER, 1)[1]
    body = body.replace(VIM_WRAP_MODELINE, "")
    body = body.replace(SHORT_VIM_WRAP_MODELINE, "")
    body = body.replace(OLD_VIM_WRAP_MODELINE, "")
    body = body.lstrip("\n")
    item.path.write_text(draft_scaffold(item, total_props) + body, encoding="utf-8")


def ensure_draft(item: WorkItem, total_props: int) -> None:
    if item.path.exists():
        normalize_draft_scaffold(item, total_props)
        return

    item.path.parent.mkdir(parents=True, exist_ok=True)
    content = draft_scaffold(item, total_props)
    item.path.write_text(content, encoding="utf-8")


def next_incomplete(items: list[WorkItem]) -> WorkItem | None:
    for item in items:
        if not item_complete(item):
            return item
    return None


def resolve_editor_command() -> list[str]:
    editor = (os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim").strip()
    command = shlex.split(editor) if editor else ["vim"]
    return command or ["vim"]


def open_editor(path: Path) -> int:
    command = resolve_editor_command()
    executable = Path(command[0]).name
    if executable in {"vim", "nvim", "vi"}:
        command = [
            *command,
            "+setlocal textwidth=79 colorcolumn=79 wrap linebreak formatoptions+=t",
        ]
    return subprocess.run([*command, str(path)], check=False).returncode


def load_target(target: BookTarget) -> tuple[dict[str, Any], list[WorkItem]]:
    structure = load_structure(target.structure_path)
    return structure, work_items(target, structure)


def print_target(target: BookTarget) -> None:
    if target.preset_name is not None:
        print(f"preset   : {target.preset_name}")
    print(f"structure: {muted_path(target.structure_path)}")
    print(f"drafts   : {muted_path(target.drafts_dir)}")


def command_write(target: BookTarget, args: list[str]) -> int:
    once = False
    rest: list[str] = []
    for token in args:
        if token == "-1":
            once = True
        else:
            rest.append(token)
    if rest:
        die("valid shape: wb <structure_json> <drafts_dir> [-1] or wb <preset> [-1]")

    structure, items = load_target(target)

    while True:
        item = next_incomplete(items)
        if item is None:
            print("complete all propositions")
            return 0

        total_props = len(structure["chapters"][item.chapter_index]["propositions"])
        ensure_draft(item, total_props)
        current = char_count(item.path)
        print(
            f"open {item.chapter_title} / {item.proposition_index} "
            f"({current}/{item.min_chars}) {muted_path(item.path)}"
        )

        code = open_editor(item.path)
        if code != 0:
            return code

        current = char_count(item.path)
        if current < item.min_chars:
            print(f"incomplete {current}/{item.min_chars}; need {item.min_chars - current} more")
            return 1

        print(f"done {current}/{item.min_chars}")
        if once:
            return 0


def command_status(target: BookTarget, args: list[str]) -> int:
    if args:
        die("valid shape: wb <structure_json> <drafts_dir> status or wb <preset> status")
    structure, items = load_target(target)
    complete = [item for item in items if item_complete(item)]
    current = next_incomplete(items)
    percent = round((len(complete) / len(items)) * 100) if items else 0

    print(structure.get("title", "Untitled"))
    print_target(target)
    print(f"progress : {len(complete)}/{len(items)} ({percent}%)")
    if current is None:
        print("next     : none")
    else:
        print(f"next     : {current.chapter_title} / {current.proposition_index}")
        print(f"chars    : {char_count(current.path)}/{current.min_chars}")
        print(f"draft    : {muted_path(current.path)}")
    return 0


def command_list(target: BookTarget, args: list[str]) -> int:
    if args:
        die("valid shape: wb <structure_json> <drafts_dir> ls or wb <preset> ls")
    _, items = load_target(target)
    for item in items:
        count = char_count(item.path)
        mark = "done" if item_complete(item) else "todo"
        print(
            f"{mark:4} {item.chapter_index + 1:02d}.{item.proposition_index:02d} "
            f"{count:4}/{item.min_chars:<4} {item.chapter_title}"
        )
    return 0


def command_show(target: BookTarget, args: list[str]) -> int:
    if args:
        die("valid shape: wb <structure_json> <drafts_dir> show or wb <preset> show")
    _, items = load_target(target)
    item = next_incomplete(items)
    if item is None:
        print("complete all propositions")
        return 0

    print(f"{item.chapter_title} / {item.proposition_index}")
    print()
    print(item.proposition)
    print()
    print(f"draft    : {muted_path(item.path)}")
    print(f"chars    : {char_count(item.path)}/{item.min_chars}")
    return 0


def command_export(target: BookTarget, args: list[str]) -> int:
    include_all = False
    output_path: Path | None = None
    rest: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if token == "-all":
            include_all = True
            i += 1
        elif token == "-o":
            if i + 1 >= len(args):
                die("-o requires an output path")
            output_path = resolve_arg_path(args[i + 1])
            i += 2
        else:
            rest.append(token)
            i += 1
    if rest:
        die(
            "valid shape: wb <structure_json> <drafts_dir> export [-all] [-o <output_md>] "
            "or wb <preset> export [-all] [-o <output_md>]"
        )

    structure, items = load_target(target)
    grouped: dict[int, list[WorkItem]] = {}
    for item in items:
        grouped.setdefault(item.chapter_index, []).append(item)

    chunks: list[str] = [f"# {structure.get('title', 'Untitled')}".strip(), ""]
    for chapter_index, chapter_items in grouped.items():
        chapter = structure["chapters"][chapter_index]
        chunks.append(f"## {chapter.get('title', f'Chapter {chapter_index + 1}')}")
        chunks.append("")
        for item in chapter_items:
            body = draft_body(item.path)
            if not body and not include_all:
                continue
            if char_count(item.path) < item.min_chars and not include_all:
                continue
            chunks.append(body)
            chunks.append("")

    output = "\n".join(chunks).rstrip() + "\n"
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        print(muted_path(output_path))
    else:
        print(output, end="")
    return 0


def command_init(args: list[str]) -> int:
    if len(args) > 1:
        die("valid shape: wb init [structure_json]")
    path = resolve_arg_path(args[0] if args else DEFAULT_STRUCTURE_NAME)
    if path.exists():
        die(f"structure already exists: {path}", code=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(BOOK_STRUCTURE_BOOTSTRAP, encoding="utf-8")
    print(muted_path(path))
    return 0


def command_preset(args: list[str]) -> int:
    if len(args) != 3:
        die("valid shape: wb preset <name> <structure_json> <drafts_dir>")
    name = args[0].strip()
    if not name:
        die("preset name must not be empty")

    structure_path = resolve_arg_path(args[1])
    drafts_dir = resolve_arg_path(args[2])
    config = load_app_config()
    presets = config.setdefault("presets", {})
    if not isinstance(presets, dict):
        die("app config presets must be a JSON object")
    presets[name] = {
        "structure": str(structure_path),
        "drafts": str(drafts_dir),
    }
    write_app_config(config)

    print(f"preset   : {name}")
    print(f"structure: {muted_path(structure_path)}")
    print(f"drafts   : {muted_path(drafts_dir)}")
    return 0


def dispatch(argv: list[str]) -> int:
    if not argv:
        die("valid shape: wb <structure_json> <drafts_dir> or wb <preset>")

    command = argv[0]
    if command == "init":
        return command_init(argv[1:])
    if command == "preset":
        return command_preset(argv[1:])

    target, action, args = parse_target(argv)
    if action == "write":
        return command_write(target, args)
    if action == "status":
        return command_status(target, args)
    if action == "list":
        return command_list(target, args)
    if action == "show":
        return command_show(target, args)
    if action == "export":
        return command_export(target, args)

    die(f"unknown command: {action}")
    return 2


def main(argv: list[str] | None = None) -> int:
    spec = AppSpec(
        app_name=APP_NAME,
        version=__version__,
        help_text=HELP_TEXT,
        install_script_path=resolve_install_script_path(__file__),
        no_args_mode="help",
        config_path_factory=app_config_path,
        config_bootstrap_text=APP_CONFIG_BOOTSTRAP,
    )
    return run_app(spec, sys.argv[1:] if argv is None else argv, dispatch)


if __name__ == "__main__":
    raise SystemExit(main())
