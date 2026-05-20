#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _version import __version__
from rgw_cli_contract import AppSpec, resolve_install_script_path, run_app


APP_NAME = "wb"
DEFAULT_BOOK_CONFIG_NAME = "wb.json"
DRAFT_MARKER = "<!-- wb:draft:start -->"

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
  open the next unfinished proposition in your editor
  # wb or wb w [-1] [-c <book_json>]
  wb
  wb w -1
  wb w -c ./book.json

  advance only after length and Orwell-rule scoring pass
  # quality gate
  score >= 7/10 via gpt-5.5

  inspect the active book without opening the editor
  # st|sh|ls [-c <book_json>]
  wb st
  wb sh
  wb ls

  export completed draft bodies into a manuscript
  # x [-all] [-o <output_md>] [-c <book_json>]
  wb x -o manuscript.md
  wb x -all

  create a generic book config in the current directory
  # init
  wb init

  edit the app config
  # conf
  wb conf
"""

APP_CONFIG_BOOTSTRAP = """{
  "book_config": "wb.json",
  "draft_dir": "drafts",
  "extension": "md",
  "min_chars": 500,
  "quality_gate": {
    "enabled": true,
    "provider": "openai",
    "model": "gpt-5.5",
    "threshold": 7,
    "rules": "orwell_6"
  }
}
"""

BOOK_CONFIG_BOOTSTRAP = """{
  "title": "Untitled Book",
  "settings": {
    "draft_dir": "drafts",
    "min_chars": 500,
    "extension": "md",
    "quality_gate": {
      "enabled": true,
      "provider": "openai",
      "model": "gpt-5.5",
      "threshold": 7,
      "rules": "orwell_6"
    }
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
        "book_config": DEFAULT_BOOK_CONFIG_NAME,
        "draft_dir": "drafts",
        "extension": "md",
        "min_chars": 500,
        "quality_gate": {
            "enabled": True,
            "provider": "openai",
            "model": "gpt-5.5",
            "threshold": 7,
            "rules": "orwell_6",
        },
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
    return config


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


def resolve_book_config(flag_value: str | None = None) -> Path:
    if flag_value:
        return Path(flag_value).expanduser().resolve()

    config = load_app_config()
    raw = str(config.get("book_config") or DEFAULT_BOOK_CONFIG_NAME)
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def parse_common(args: list[str]) -> tuple[Path, list[str]]:
    config_flag: str | None = None
    rest: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if token == "-c":
            if i + 1 >= len(args):
                die("-c requires a book config path")
            config_flag = args[i + 1]
            i += 2
            continue
        rest.append(token)
        i += 1
    return resolve_book_config(config_flag), rest


def load_book_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"book config not found: {path}\nrun wb init or pass -c <book_json>")
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")

    if not isinstance(config, dict):
        die("book config root must be a JSON object")
    if not isinstance(config.get("chapters"), list) or not config["chapters"]:
        die("book config must contain a non-empty chapters array")
    return config


def book_settings(book_config: dict[str, Any]) -> dict[str, Any]:
    raw = book_config.get("settings", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        die("book settings must be an object")
    merged = load_app_config()
    for key, value in raw.items():
        if key == "quality_gate" and isinstance(value, dict):
            gate = dict(merged.get("quality_gate", {}))
            gate.update(value)
            merged["quality_gate"] = gate
        else:
            merged[key] = value
    return merged


def min_chars_for(book_config: dict[str, Any], chapter: dict[str, Any]) -> int:
    value = chapter.get("min_chars", book_settings(book_config).get("min_chars", 500))
    try:
        return int(value)
    except (TypeError, ValueError):
        die(f"invalid min_chars value: {value!r}")


def draft_root(book_config_path: Path, book_config: dict[str, Any]) -> Path:
    draft_dir = book_settings(book_config).get("draft_dir", "drafts")
    return (book_config_path.parent / str(draft_dir)).resolve()


def work_items(book_config_path: Path, book_config: dict[str, Any]) -> list[WorkItem]:
    items: list[WorkItem] = []
    root = draft_root(book_config_path, book_config)
    extension = str(book_settings(book_config).get("extension", "md")).lstrip(".")

    for chapter_index, chapter in enumerate(book_config["chapters"]):
        if not isinstance(chapter, dict):
            die(f"chapter {chapter_index + 1} must be an object")

        title = str(chapter.get("title", f"Chapter {chapter_index + 1}"))
        propositions = chapter.get("propositions")
        if not isinstance(propositions, list) or not propositions:
            die(f"{title}: propositions must be a non-empty array")

        chapter_dir = root / f"{chapter_index:02d}-{slugify(title)}"
        chapter_min_chars = min_chars_for(book_config, chapter)

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
    return content.split(DRAFT_MARKER, 1)[1].strip()


def char_count(path: Path) -> int:
    return len(draft_body(path))


def body_hash(path: Path) -> str:
    return hashlib.sha256(draft_body(path).encode("utf-8")).hexdigest()


def quality_gate(book_config: dict[str, Any]) -> dict[str, Any]:
    raw = book_settings(book_config).get("quality_gate", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        die("quality_gate must be an object")

    gate = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-5.5",
        "threshold": 7,
        "rules": "orwell_6",
    }
    gate.update(raw)
    return gate


def gate_enabled(book_config: dict[str, Any]) -> bool:
    return bool(quality_gate(book_config).get("enabled", True))


def state_path(item: WorkItem, book_config_path: Path, book_config: dict[str, Any]) -> Path:
    root = draft_root(book_config_path, book_config) / ".wb-state"
    rel = item.path.relative_to(draft_root(book_config_path, book_config))
    return root / rel.with_suffix(rel.suffix + ".json")


def read_state(item: WorkItem, book_config_path: Path, book_config: dict[str, Any]) -> dict[str, Any]:
    path = state_path(item, book_config_path, book_config)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def write_state(
    item: WorkItem,
    book_config_path: Path,
    book_config: dict[str, Any],
    state: dict[str, Any],
) -> None:
    path = state_path(item, book_config_path, book_config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def item_complete(item: WorkItem, book_config_path: Path, book_config: dict[str, Any]) -> bool:
    if char_count(item.path) < item.min_chars:
        return False
    if not gate_enabled(book_config):
        return True

    state = read_state(item, book_config_path, book_config)
    return (
        state.get("body_hash") == body_hash(item.path)
        and bool(state.get("pass"))
        and int(state.get("score", 0)) >= int(quality_gate(book_config).get("threshold", 7))
    )


def ensure_draft(item: WorkItem, total_props: int) -> None:
    if item.path.exists():
        return

    item.path.parent.mkdir(parents=True, exist_ok=True)
    wrapped = "\n".join(
        f"> {line}" if line else ">"
        for line in textwrap.wrap(item.proposition, width=88)
    )
    content = f"""# {item.chapter_title}

Proposition {item.proposition_index} of {total_props}

## Proposition

{wrapped}

## Draft

Write below this marker. The proposition text above is scaffolding and does not count.
Completion requires at least {item.min_chars} characters below the marker.

{DRAFT_MARKER}
"""
    item.path.write_text(content, encoding="utf-8")


def next_incomplete(
    items: list[WorkItem],
    book_config_path: Path,
    book_config: dict[str, Any],
) -> WorkItem | None:
    for item in items:
        if not item_complete(item, book_config_path, book_config):
            return item
    return None


def resolve_editor_command() -> list[str]:
    editor = (os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim").strip()
    command = shlex.split(editor) if editor else ["vim"]
    return command or ["vim"]


def open_editor(path: Path) -> int:
    return subprocess.run([*resolve_editor_command(), str(path)], check=False).returncode


def openai_api_key_from_bashrc() -> str:
    result = subprocess.run(
        [
            "bash",
            "-lc",
            'source "$HOME/.bashrc" >/dev/null 2>&1 || true; printf "%s" "${OPENAI_API_KEY:-}"',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    key = result.stdout.strip()
    if key:
        return key
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    die("OPENAI_API_KEY not found after sourcing ~/.bashrc", code=1)


def extract_response_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    parts: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict):
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "\n".join(parts).strip()


def score_with_openai(item: WorkItem, book_config: dict[str, Any]) -> dict[str, Any]:
    gate = quality_gate(book_config)
    model = str(gate.get("model") or "gpt-5.5")
    threshold = int(gate.get("threshold", 7))
    body = draft_body(item.path)
    api_key = openai_api_key_from_bashrc()

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "score": {"type": "integer"},
            "pass": {"type": "boolean"},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "revision_targets": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["score", "pass", "reasons", "revision_targets"],
    }

    system = (
        "You are a strict prose editor. Score only the submitted draft body, "
        "not the proposition text. Evaluate compliance with George Orwell's six rules: "
        "avoid stale figures of speech; use short words when possible; cut words that can be cut; "
        "prefer active voice; avoid foreign phrases, scientific words, and jargon when plain English works; "
        "break these rules before writing something barbarous. Return JSON only. "
        f"Set pass to true if and only if score is at least {threshold}."
    )
    user = (
        f"Chapter: {item.chapter_title}\n"
        f"Proposition: {item.proposition}\n\n"
        "Draft body:\n"
        f"{body}\n\n"
        "Give a 0-10 score for Orwell-rule compliance. If the score is below the threshold, "
        "explain the main fixes in plain English."
    )
    request_payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system}]},
            {"role": "user", "content": [{"type": "input_text", "text": user}]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "orwell_gate",
                "schema": schema,
                "strict": True,
            }
        },
        "reasoning": {"effort": "low"},
        "max_output_tokens": 800,
        "store": False,
    }
    data = json.dumps(request_payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        die(f"OpenAI scoring failed: HTTP {exc.code}: {detail[:500]}", code=1)
    except urllib.error.URLError as exc:
        die(f"OpenAI scoring failed: {exc.reason}", code=1)

    response_payload = json.loads(raw)
    text = extract_response_text(response_payload)
    try:
        score = json.loads(text)
    except json.JSONDecodeError:
        die("OpenAI scoring returned invalid JSON", code=1)

    if not isinstance(score, dict):
        die("OpenAI scoring returned the wrong shape", code=1)
    score_value = int(score.get("score", 0))
    score["score"] = max(0, min(10, score_value))
    score["pass"] = bool(score.get("pass")) and score["score"] >= threshold
    score["threshold"] = threshold
    score["model"] = model
    return score


def print_score(score: dict[str, Any]) -> None:
    status = "pass" if score.get("pass") else "fail"
    print(f"score    : {score.get('score')}/10 {status}")
    reasons = score.get("reasons", [])
    if isinstance(reasons, list) and reasons:
        print("why      :")
        for reason in reasons[:6]:
            print(f"- {reason}")
    targets = score.get("revision_targets", [])
    if isinstance(targets, list) and targets:
        print("fix      :")
        for target in targets[:6]:
            print(f"- {target}")


def run_quality_gate(
    item: WorkItem,
    book_config_path: Path,
    book_config: dict[str, Any],
) -> bool:
    if not gate_enabled(book_config):
        return True

    print("scoring  : Orwell gate via OpenAI")
    score = score_with_openai(item, book_config)
    score["body_hash"] = body_hash(item.path)
    write_state(item, book_config_path, book_config, score)
    print_score(score)
    return bool(score.get("pass"))


def command_write(book_config_path: Path, args: list[str]) -> int:
    once = False
    rest: list[str] = []
    for token in args:
        if token == "-1":
            once = True
        else:
            rest.append(token)
    if rest:
        die("valid shape: wb w [-1] [-c <book_json>]")

    book_config = load_book_config(book_config_path)
    items = work_items(book_config_path, book_config)

    while True:
        item = next_incomplete(items, book_config_path, book_config)
        if item is None:
            print("complete all propositions")
            return 0

        total_props = len(book_config["chapters"][item.chapter_index]["propositions"])
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

        if not run_quality_gate(item, book_config_path, book_config):
            print("blocked  : revise this proposition before moving on")
            return 1

        print(f"done {current}/{item.min_chars}")
        if once:
            return 0


def command_status(book_config_path: Path, args: list[str]) -> int:
    if args:
        die("valid shape: wb st [-c <book_json>]")
    book_config = load_book_config(book_config_path)
    items = work_items(book_config_path, book_config)
    complete = [item for item in items if item_complete(item, book_config_path, book_config)]
    current = next_incomplete(items, book_config_path, book_config)

    print(book_config.get("title", "Untitled"))
    print(f"config   : {muted_path(book_config_path)}")
    print(f"progress : {len(complete)}/{len(items)}")
    if current is None:
        print("next     : none")
    else:
        print(f"next     : {current.chapter_title} / {current.proposition_index}")
        print(f"chars    : {char_count(current.path)}/{current.min_chars}")
        if gate_enabled(book_config) and char_count(current.path) >= current.min_chars:
            state = read_state(current, book_config_path, book_config)
            if state.get("body_hash") == body_hash(current.path):
                print(f"score    : {state.get('score', 'unscored')}/10")
            else:
                print("score    : unscored")
        print(f"draft    : {muted_path(current.path)}")
    return 0


def command_list(book_config_path: Path, args: list[str]) -> int:
    if args:
        die("valid shape: wb ls [-c <book_json>]")
    book_config = load_book_config(book_config_path)
    for item in work_items(book_config_path, book_config):
        count = char_count(item.path)
        mark = "done" if item_complete(item, book_config_path, book_config) else "todo"
        print(
            f"{mark:4} {item.chapter_index + 1:02d}.{item.proposition_index:02d} "
            f"{count:4}/{item.min_chars:<4} {item.chapter_title}"
        )
    return 0


def command_show(book_config_path: Path, args: list[str]) -> int:
    if args:
        die("valid shape: wb sh [-c <book_json>]")
    book_config = load_book_config(book_config_path)
    item = next_incomplete(work_items(book_config_path, book_config), book_config_path, book_config)
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


def command_export(book_config_path: Path, args: list[str]) -> int:
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
            output_path = Path(args[i + 1]).expanduser()
            i += 2
        else:
            rest.append(token)
            i += 1
    if rest:
        die("valid shape: wb x [-all] [-o <output_md>] [-c <book_json>]")

    book_config = load_book_config(book_config_path)
    grouped: dict[int, list[WorkItem]] = {}
    for item in work_items(book_config_path, book_config):
        grouped.setdefault(item.chapter_index, []).append(item)

    chunks: list[str] = [f"# {book_config.get('title', 'Untitled')}".strip(), ""]
    for chapter_index, chapter_items in grouped.items():
        chapter = book_config["chapters"][chapter_index]
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
        output_path.write_text(output, encoding="utf-8")
        print(muted_path(output_path))
    else:
        print(output, end="")
    return 0


def command_init(args: list[str]) -> int:
    if args:
        die("valid shape: wb init")
    path = resolve_book_config()
    if path.exists():
        die(f"book config already exists: {path}", code=1)
    path.write_text(BOOK_CONFIG_BOOTSTRAP, encoding="utf-8")
    print(muted_path(path))
    return 0


def dispatch(argv: list[str]) -> int:
    if not argv:
        return command_write(resolve_book_config(), [])

    command = argv[0]
    if command == "init":
        return command_init(argv[1:])

    book_config_path, args = parse_common(argv[1:])

    if command == "w":
        return command_write(book_config_path, args)
    if command == "st":
        return command_status(book_config_path, args)
    if command == "ls":
        return command_list(book_config_path, args)
    if command == "sh":
        return command_show(book_config_path, args)
    if command == "x":
        return command_export(book_config_path, args)

    die(f"unknown command: {command}")
    return 2


def main(argv: list[str] | None = None) -> int:
    spec = AppSpec(
        app_name=APP_NAME,
        version=__version__,
        help_text=HELP_TEXT,
        install_script_path=resolve_install_script_path(__file__),
        no_args_mode="dispatch",
        config_path_factory=app_config_path,
        config_bootstrap_text=APP_CONFIG_BOOTSTRAP,
    )
    return run_app(spec, sys.argv[1:] if argv is None else argv, dispatch)


if __name__ == "__main__":
    raise SystemExit(main())
