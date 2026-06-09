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


APP_NAME = "wb"
DEFAULT_STRUCTURE_NAME = "structure.json"
DRAFT_MARKER = "<!-- wb:draft:start -->"
VIM_WRAP_MODELINE = "<!-- wb: vim wraps prose at 79 columns -->"
SHORT_VIM_WRAP_MODELINE = "<!-- vim: setlocal tw=79 cc=79 wrap lbr fo+=t: -->"
OLD_VIM_WRAP_MODELINE = "<!-- vim: setlocal textwidth=79 colorcolumn=79 wrap linebreak formatoptions+=t: -->"
SCAFFOLD_WIDTH = 79
ANSI_GRAY = "\033[38;5;245m"
ANSI_RESET = "\033[0m"
TUI_PAIR_NORMAL = 1
TUI_PAIR_MUTED = 2
TUI_PAIR_STRONG = 3
TUI_PAIR_SELECTED = 4
INSTALL_SCRIPT = (
    Path(sys.executable).resolve().parent / "install.sh"
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().with_name("install.sh")
)

HELP_TEXT = """Writer's Block
write long work one proposition at a time

global actions:
  wb help
    show this help
  wb version
    print the installed version
  wb list
    list saved wb projects
  wb tui
    select a saved book and browse drafts
  wb upgrade
    upgrade to the latest release

features:
  create a generic book structure file
  # init [structure_json]
  wb init
  wb init ./structure.json

  save a named preset
  # preset save <name> structure <structure_json> drafts <drafts_dir>
  wb preset save "an eye for an eye" structure ./structure.json drafts ./drafts

  browse saved books in the terminal UI
  # tui
  wb tui

  open the next unfinished proposition in your editor
  # write <structure_json> drafts <drafts_dir> [first]
  wb write ./structure.json drafts ./drafts
  wb write ./structure.json drafts ./drafts first

  use a named preset for writing, inspection, or export
  # use <preset> [status|list|show|export] [all] [to <output_md>]
  wb use "an eye for an eye"
  wb use "an eye for an eye" status
  wb use "an eye for an eye" export to manuscript.md

  export completed draft bodies into a manuscript
  # export <structure_json> drafts <drafts_dir> [all] [to <output_md>]
  wb export ./structure.json drafts ./drafts to manuscript.md
  wb export ./structure.json drafts ./drafts all

  edit generic app defaults and machine-local presets
  # config
  wb config
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


def muted(text: str) -> str:
    if not sys.stdout.isatty() or "NO_COLOR" in os.environ:
        return text
    return f"{ANSI_GRAY}{text}{ANSI_RESET}"


def print_help() -> None:
    print(muted(HELP_TEXT.rstrip()))


def upgrade_app() -> int:
    if not INSTALL_SCRIPT.exists():
        print(f"install.sh is missing: {INSTALL_SCRIPT}", file=sys.stderr)
        return 1
    return subprocess.run(["bash", str(INSTALL_SCRIPT), "upgrade"], check=False).returncode


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


@dataclass(frozen=True)
class TuiProject:
    name: str
    title: str
    target: BookTarget
    items: list[WorkItem]
    complete_count: int
    current_index: int


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
            "run wb preset save <name> structure <structure_json> drafts <drafts_dir> "
            "or wb config"
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


def target_from_preset_record(name: str, raw: Any, base: Path) -> BookTarget | None:
    if not isinstance(raw, dict):
        return None

    structure = raw.get("structure")
    drafts = raw.get("drafts")
    if not isinstance(structure, str) or not structure.strip():
        return None
    if not isinstance(drafts, str) or not drafts.strip():
        return None

    return BookTarget(
        structure_path=resolve_path(structure, base),
        drafts_dir=resolve_path(drafts, base),
        preset_name=name,
    )


def load_tui_projects() -> list[TuiProject]:
    config = load_app_config()
    presets = config.get("presets", {})
    if not isinstance(presets, dict):
        die("app config presets must be a JSON object")

    projects: list[TuiProject] = []
    base = app_config_path().parent
    for name in sorted(presets, key=str.casefold):
        target = target_from_preset_record(name, presets[name], base)
        if target is None:
            continue

        structure, items = load_target(target)
        complete = [item for item in items if item_complete(item)]
        current = next_incomplete(items)
        if current is None:
            current_index = max(len(items) - 1, 0)
        else:
            current_index = items.index(current)
        projects.append(
            TuiProject(
                name=name,
                title=str(structure.get("title", "Untitled")),
                target=target,
                items=items,
                complete_count=len(complete),
                current_index=current_index,
            )
        )
    return projects


def status_word(item: WorkItem) -> str:
    return "done" if item_complete(item) else "todo"


def wrap_display_text(text: str, width: int) -> list[str]:
    safe_width = max(width, 20)
    lines: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(raw_line, width=safe_width) or [""])
    return lines


def tui_project_row(project: TuiProject) -> str:
    total = len(project.items)
    percent = round((project.complete_count / total) * 100) if total else 0
    return f"{project.name}  {project.complete_count}/{total} ({percent}%)  {project.title}"


def tui_item_header(project: TuiProject, index: int) -> str:
    item = project.items[index]
    return (
        f"{project.title} - {index + 1}/{len(project.items)} "
        f"{status_word(item)} {char_count(item.path)}/{item.min_chars}"
    )


def tui_item_lines(project: TuiProject, index: int, width: int) -> list[str]:
    item = project.items[index]
    body = draft_body(item.path)
    lines = [
        f"{item.chapter_title} / {item.proposition_index}",
        f"draft: {muted_path(item.path)}",
        "",
        "Proposition",
        "",
    ]
    lines.extend(wrap_display_text(item.proposition, width))
    lines.extend(["", "Draft", ""])
    if body:
        lines.extend(wrap_display_text(body, width))
    else:
        lines.append("(empty draft)")
    return lines


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


def parse_structure_drafts(args: list[str], shape: str) -> tuple[BookTarget, list[str]]:
    if len(args) < 3 or args[1] != "drafts":
        die(shape)
    return (
        BookTarget(
            structure_path=resolve_arg_path(args[0]),
            drafts_dir=resolve_arg_path(args[2]),
        ),
        args[3:],
    )


def parse_export_args(args: list[str], shape: str) -> tuple[bool, Path | None]:
    include_all = False
    output_path: Path | None = None
    i = 0
    while i < len(args):
        token = args[i]
        if token == "all":
            include_all = True
            i += 1
            continue
        if token == "to":
            if output_path is not None:
                die(shape)
            if i + 1 >= len(args):
                die("to requires an output path")
            output_path = resolve_arg_path(args[i + 1])
            i += 2
            continue
        die(shape)
    return include_all, output_path


def command_write(target: BookTarget, args: list[str]) -> int:
    if args == ["first"]:
        once = True
    elif not args:
        once = False
    else:
        die("valid shape: wb write <structure_json> drafts <drafts_dir> [first]")

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
        die("valid shape: wb use <preset> status")
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


def command_project_list(args: list[str]) -> int:
    if args:
        die("valid shape: wb list")

    config = load_app_config()
    presets = config.get("presets", {})
    if not isinstance(presets, dict):
        die("app config presets must be a JSON object")
    if not presets:
        print("no wb projects saved")
        print("save one with: wb preset save <name> structure <structure_json> drafts <drafts_dir>")
        return 0

    print("wb projects")
    base = app_config_path().parent
    for index, name in enumerate(sorted(presets, key=str.casefold)):
        raw = presets[name]
        if index:
            print()
        print(name)

        if not isinstance(raw, dict):
            print("  status   : invalid preset")
            print("  error    : preset must be a JSON object")
            continue

        structure = raw.get("structure")
        drafts = raw.get("drafts")
        if not isinstance(structure, str) or not structure.strip():
            print("  status   : invalid preset")
            print("  error    : missing structure path")
            continue
        if not isinstance(drafts, str) or not drafts.strip():
            print("  status   : invalid preset")
            print("  error    : missing drafts dir")
            continue

        target = BookTarget(
            structure_path=resolve_path(structure, base),
            drafts_dir=resolve_path(drafts, base),
            preset_name=name,
        )
        structure_data, items = load_target(target)
        complete = [item for item in items if item_complete(item)]
        current = next_incomplete(items)
        percent = round((len(complete) / len(items)) * 100) if items else 0

        print(f"  title    : {structure_data.get('title', 'Untitled')}")
        print(f"  progress : {len(complete)}/{len(items)} ({percent}%)")
        if current is None:
            print("  next     : none")
        else:
            print(f"  next     : {current.chapter_title} / {current.proposition_index}")
            print(f"  chars    : {char_count(current.path)}/{current.min_chars}")
        print(f"  structure: {muted_path(target.structure_path)}")
        print(f"  drafts   : {muted_path(target.drafts_dir)}")
    return 0


def command_list(target: BookTarget, args: list[str]) -> int:
    if args:
        die("valid shape: wb use <preset> list")
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
        die("valid shape: wb use <preset> show")
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
    include_all, output_path = parse_export_args(
        args,
        "valid shape: wb export <structure_json> drafts <drafts_dir> [all] [to <output_md>]",
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
    if len(args) != 6 or args[0] != "save" or args[2] != "structure" or args[4] != "drafts":
        die("valid shape: wb preset save <name> structure <structure_json> drafts <drafts_dir>")
    name = args[1].strip()
    if not name:
        die("preset name must not be empty")

    structure_path = resolve_arg_path(args[3])
    drafts_dir = resolve_arg_path(args[5])
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


def command_config(args: list[str]) -> int:
    if args:
        die("valid shape: wb config")
    path = app_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(APP_CONFIG_BOOTSTRAP, encoding="utf-8")
    return subprocess.run([*resolve_editor_command(), str(path)], check=False).returncode


def setup_tui_screen(stdscr: Any, curses_module: Any) -> dict[str, int]:
    attrs = {
        "normal": 0,
        "muted": getattr(curses_module, "A_DIM", 0),
        "strong": getattr(curses_module, "A_BOLD", 0),
        "selected": getattr(curses_module, "A_BOLD", 0),
    }

    try:
        curses_module.curs_set(0)
    except Exception:
        pass

    try:
        curses_module.start_color()
        curses_module.use_default_colors()
        if curses_module.has_colors():
            curses_module.init_pair(TUI_PAIR_NORMAL, curses_module.COLOR_WHITE, -1)
            curses_module.init_pair(TUI_PAIR_MUTED, curses_module.COLOR_WHITE, -1)
            curses_module.init_pair(TUI_PAIR_STRONG, curses_module.COLOR_WHITE, -1)
            curses_module.init_pair(TUI_PAIR_SELECTED, curses_module.COLOR_CYAN, -1)
            attrs = {
                "normal": curses_module.color_pair(TUI_PAIR_NORMAL),
                "muted": curses_module.color_pair(TUI_PAIR_MUTED) | getattr(curses_module, "A_DIM", 0),
                "strong": curses_module.color_pair(TUI_PAIR_STRONG) | getattr(curses_module, "A_BOLD", 0),
                "selected": curses_module.color_pair(TUI_PAIR_SELECTED) | getattr(curses_module, "A_BOLD", 0),
            }
            stdscr.bkgd(" ", attrs["normal"])
    except Exception:
        pass

    return attrs


def screen_add(stdscr: Any, y: int, x: int, text: str, attr: int = 0) -> None:
    height, width = stdscr.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= width:
        return
    max_chars = max(width - x - 1, 0)
    if max_chars <= 0:
        return
    try:
        stdscr.addnstr(y, x, text, max_chars, attr)
    except Exception:
        return


def tui_project_picker(
    stdscr: Any,
    curses_module: Any,
    projects: list[TuiProject],
    selected: int,
    attrs: dict[str, int],
) -> int | None:
    selected = max(0, min(selected, len(projects) - 1))
    while True:
        height, width = stdscr.getmaxyx()
        body_height = max(height - 4, 1)
        offset = min(max(0, selected - body_height // 2), max(len(projects) - body_height, 0))

        stdscr.erase()
        screen_add(stdscr, 0, 0, "wb books", attrs["strong"])
        screen_add(stdscr, 1, 0, "enter select  j/k move  q quit", attrs["muted"])

        for row, index in enumerate(range(offset, min(offset + body_height, len(projects))), start=3):
            marker = ">" if index == selected else " "
            line = f"{marker} {tui_project_row(projects[index])}"
            attr = attrs["selected"] if index == selected else attrs["normal"]
            screen_add(stdscr, row, 0, line, attr)

        if height > 0:
            screen_add(stdscr, height - 1, 0, f"{len(projects)} project(s)", attrs["muted"])
        stdscr.refresh()
        key = stdscr.getch()

        if key in (ord("q"), 27):
            return None
        if key in (ord("j"), curses_module.KEY_DOWN):
            selected = min(selected + 1, len(projects) - 1)
            continue
        if key in (ord("k"), curses_module.KEY_UP):
            selected = max(selected - 1, 0)
            continue
        if key in (10, 13, curses_module.KEY_ENTER):
            return selected


def tui_project_reader(stdscr: Any, curses_module: Any, project: TuiProject, attrs: dict[str, int]) -> str:
    index = project.current_index
    scroll = 0
    while True:
        height, width = stdscr.getmaxyx()
        content_height = max(height - 3, 1)
        content_width = max(width - 1, 20)
        lines = tui_item_lines(project, index, content_width)
        max_scroll = max(len(lines) - content_height, 0)
        scroll = min(scroll, max_scroll)

        stdscr.erase()
        screen_add(stdscr, 0, 0, tui_item_header(project, index), attrs["strong"])
        screen_add(stdscr, 1, 0, "n next  p previous  j/k scroll  b books  q quit", attrs["muted"])

        for row, line in enumerate(lines[scroll : scroll + content_height], start=2):
            screen_add(stdscr, row, 0, line, attrs["normal"])

        if height > 0:
            screen_add(stdscr, height - 1, 0, f"scroll {scroll}/{max_scroll}", attrs["muted"])
        stdscr.refresh()
        key = stdscr.getch()

        if key in (ord("q"), 27):
            return "quit"
        if key == ord("b"):
            return "books"
        if key == ord("n"):
            index = min(index + 1, len(project.items) - 1)
            scroll = 0
            continue
        if key == ord("p"):
            index = max(index - 1, 0)
            scroll = 0
            continue
        if key in (ord("j"), curses_module.KEY_DOWN):
            scroll = min(scroll + 1, max_scroll)
            continue
        if key in (ord("k"), curses_module.KEY_UP):
            scroll = max(scroll - 1, 0)
            continue
        if key == ord("g"):
            scroll = 0
            continue
        if key == ord("G"):
            scroll = max_scroll
            continue


def run_tui(stdscr: Any, curses_module: Any, projects: list[TuiProject]) -> int:
    attrs = setup_tui_screen(stdscr, curses_module)
    selected = 0
    while True:
        picked = tui_project_picker(stdscr, curses_module, projects, selected, attrs)
        if picked is None:
            return 0
        selected = picked
        result = tui_project_reader(stdscr, curses_module, projects[picked], attrs)
        if result == "quit":
            return 0


def command_tui(args: list[str]) -> int:
    if args:
        die("valid shape: wb tui")

    projects = load_tui_projects()
    if not projects:
        print("no wb projects saved")
        print("save one with: wb preset save <name> structure <structure_json> drafts <drafts_dir>")
        return 0

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        die("wb tui requires an interactive terminal", code=1)

    import curses

    try:
        return curses.wrapper(lambda stdscr: run_tui(stdscr, curses, projects))
    except KeyboardInterrupt:
        return 0


def command_use(args: list[str]) -> int:
    if not args:
        die("valid shape: wb use <preset> [status|list|show|export]")
    target = resolve_preset(args[0])
    if len(args) == 1:
        return command_write(target, [])
    action = args[1]
    rest = args[2:]
    if action == "status":
        return command_status(target, rest)
    if action == "list":
        return command_list(target, rest)
    if action == "show":
        return command_show(target, rest)
    if action == "export":
        include_all, output_path = parse_export_args(
            rest,
            "valid shape: wb use <preset> export [all] [to <output_md>]",
        )
        export_args: list[str] = []
        if include_all:
            export_args.append("all")
        if output_path is not None:
            export_args.extend(["to", str(output_path)])
        return command_export(target, export_args)
    die("valid shape: wb use <preset> [status|list|show|export]")
    return 2


def dispatch(argv: list[str]) -> int:
    if not argv:
        die("valid shape: wb write <structure_json> drafts <drafts_dir> [first]")

    command = argv[0]
    if command == "init":
        return command_init(argv[1:])
    if command == "preset":
        return command_preset(argv[1:])
    if command == "config":
        return command_config(argv[1:])
    if command == "list":
        return command_project_list(argv[1:])
    if command == "tui":
        return command_tui(argv[1:])
    if command == "write":
        target, rest = parse_structure_drafts(
            argv[1:],
            "valid shape: wb write <structure_json> drafts <drafts_dir> [first]",
        )
        return command_write(target, rest)
    if command == "use":
        return command_use(argv[1:])
    if command == "export":
        target, rest = parse_structure_drafts(
            argv[1:],
            "valid shape: wb export <structure_json> drafts <drafts_dir> [all] [to <output_md>]",
        )
        return command_export(target, rest)

    die(
        "valid shape: wb init [structure_json] | wb list | wb tui | "
        "wb write <structure_json> drafts <drafts_dir> [first]"
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("ESCDELAY", "25")
    os.environ.setdefault("TERM", "xterm-256color")

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args == ["help"]:
        print_help()
        return 0
    if args == ["version"]:
        print(__version__)
        return 0
    if args == ["upgrade"]:
        return upgrade_app()
    if args[0] in {"help", "version", "upgrade"}:
        die("global actions must be used alone")
    return dispatch(args)


if __name__ == "__main__":
    raise SystemExit(main())
