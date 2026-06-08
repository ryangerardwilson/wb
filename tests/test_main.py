from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WB = ROOT / "wb"
sys.path.insert(0, str(ROOT))
import main as wb_main


def run_wb(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [str(WB), *args],
        cwd=cwd,
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )


def write_structure(path: Path, min_chars: int = 1, proposition_count: int = 1) -> None:
    propositions = [f"Argue thing {index}." for index in range(1, proposition_count + 1)]
    path.write_text(
        json.dumps(
            {
                "title": "Small",
                "settings": {"min_chars": min_chars, "extension": "md"},
                "chapters": [{"title": "One", "propositions": propositions}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class MainTests(unittest.TestCase):
    def test_help_version_and_no_arg_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {"XDG_CONFIG_HOME": str(Path(tmp) / "config")}

            bare_result = run_wb(cwd=ROOT, env=env)
            help_result = run_wb("help", cwd=ROOT, env=env)
            version_result = run_wb("version", cwd=ROOT, env=env)

        self.assertEqual(bare_result.returncode, 0)
        self.assertEqual(help_result.returncode, 0)
        self.assertEqual(bare_result.stdout, help_result.stdout)
        self.assertIn("Writer's Block", help_result.stdout)
        self.assertIn("global actions:", help_result.stdout)
        self.assertIn("features:", help_result.stdout)
        self.assertIn("wb list", help_result.stdout)
        self.assertIn("wb upgrade", help_result.stdout)
        self.assertIn('wb use "an eye for an eye" status', help_result.stdout)
        self.assertNotIn("usage:", help_result.stdout)
        self.assertNotIn("--help", help_result.stdout)
        self.assertNotIn('wb "an eye for an eye"', help_result.stdout)
        self.assertEqual(version_result.stdout, "0.0.0\n")

    def test_upgrade_delegates_to_installer(self) -> None:
        completed = subprocess.CompletedProcess(["bash"], 0)
        with mock.patch.object(wb_main.subprocess, "run", return_value=completed) as run:
            result = wb_main.main(["upgrade"])

        self.assertEqual(result, 0)
        run.assert_called_once_with(["bash", str(wb_main.INSTALL_SCRIPT), "upgrade"], check=False)

    def test_config_creates_xdg_app_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            env = {"XDG_CONFIG_HOME": str(xdg), "EDITOR": "true", "VISUAL": ""}

            result = run_wb("config", cwd=ROOT, env=env)
            config_path = xdg / "wb" / "config.json"

            self.assertEqual(result.returncode, 0)
            self.assertTrue(config_path.exists())
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config, {"extension": "md", "min_chars": 500, "presets": {}})

    def test_init_and_preset_status_use_explicit_structure_and_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            env = {"XDG_CONFIG_HOME": str(cwd / "xdg")}

            init_result = run_wb("init", "structure.json", cwd=cwd, env=env)
            preset_result = run_wb(
                "preset",
                "save",
                "small",
                "structure",
                "structure.json",
                "drafts",
                "drafts",
                cwd=cwd,
                env=env,
            )
            status_result = run_wb("use", "small", "status", cwd=cwd, env=env)

        self.assertEqual(init_result.returncode, 0)
        self.assertEqual(preset_result.returncode, 0)
        self.assertEqual(status_result.returncode, 0)
        self.assertIn("Untitled Book", status_result.stdout)
        self.assertIn("structure: structure.json", status_result.stdout)
        self.assertIn("drafts   : drafts", status_result.stdout)
        self.assertIn("progress : 0/1 (0%)", status_result.stdout)
        self.assertNotIn("score", status_result.stdout)

    def test_preset_command_writes_xdg_config_and_status_uses_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            xdg = cwd / "xdg"
            structure = cwd / "structure.json"
            drafts = cwd / "drafts"
            write_structure(structure)
            env = {"XDG_CONFIG_HOME": str(xdg)}

            preset_result = run_wb(
                "preset",
                "save",
                "an eye for an eye",
                "structure",
                str(structure),
                "drafts",
                str(drafts),
                cwd=ROOT,
                env=env,
            )
            status_result = run_wb("use", "an eye for an eye", "status", cwd=ROOT, env=env)
            config = json.loads((xdg / "wb" / "config.json").read_text(encoding="utf-8"))

        self.assertEqual(preset_result.returncode, 0)
        self.assertEqual(status_result.returncode, 0)
        self.assertEqual(
            config["presets"]["an eye for an eye"],
            {"structure": str(structure), "drafts": str(drafts)},
        )
        self.assertIn("preset   : an eye for an eye", status_result.stdout)
        self.assertIn("progress : 0/1 (0%)", status_result.stdout)

    def test_list_reports_saved_projects_from_xdg_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            xdg = cwd / "xdg"
            structure = cwd / "structure.json"
            drafts = cwd / "drafts"
            write_structure(structure, min_chars=5, proposition_count=2)
            target = wb_main.BookTarget(structure_path=structure, drafts_dir=drafts)
            loaded = wb_main.load_structure(structure)
            first_item = wb_main.work_items(target, loaded)[0]
            wb_main.ensure_draft(first_item, 2)
            first_item.path.write_text(
                first_item.path.read_text(encoding="utf-8") + "\nfirst body",
                encoding="utf-8",
            )
            env = {"XDG_CONFIG_HOME": str(xdg)}

            preset_result = run_wb(
                "preset",
                "save",
                "small",
                "structure",
                str(structure),
                "drafts",
                str(drafts),
                cwd=cwd,
                env=env,
            )
            list_result = run_wb("list", cwd=cwd, env=env)

        self.assertEqual(preset_result.returncode, 0)
        self.assertEqual(list_result.returncode, 0)
        self.assertIn("wb projects", list_result.stdout)
        self.assertIn("small", list_result.stdout)
        self.assertIn("title    : Small", list_result.stdout)
        self.assertIn("progress : 1/2 (50%)", list_result.stdout)
        self.assertIn("next     : One / 2", list_result.stdout)
        self.assertIn("chars    : 0/5", list_result.stdout)
        self.assertIn("structure: structure.json", list_result.stdout)
        self.assertIn("drafts   : drafts", list_result.stdout)

    def test_write_counts_only_below_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            structure = cwd / "structure.json"
            drafts = cwd / "drafts"
            write_structure(structure, min_chars=1)
            editor = cwd / "editor.sh"
            editor.write_text("#!/usr/bin/env bash\nprintf 'x' >> \"$1\"\n", encoding="utf-8")
            editor.chmod(0o755)
            env = {
                "XDG_CONFIG_HOME": str(cwd / "xdg"),
                "EDITOR": str(editor),
                "VISUAL": "",
            }

            result = run_wb("write", str(structure), "drafts", str(drafts), "first", cwd=cwd, env=env)
            draft = drafts / "00-one" / "01.md"

            self.assertEqual(result.returncode, 0)
            self.assertTrue(draft.exists())
            text = draft.read_text(encoding="utf-8")
            self.assertIn("vim wraps prose at 79 columns", text)
            self.assertNotIn("setlocal tw=79", text)
            self.assertNotIn("textwidth=79", text)
            long_lines = [
                (number, len(line), line)
                for number, line in enumerate(text.splitlines(), start=1)
                if len(line) > 79
            ]
            self.assertEqual(long_lines, [])
            self.assertIn("done 1/1", result.stdout)
            self.assertNotIn("scoring", result.stdout)

    def test_status_reports_completed_propositions_after_drafts_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            structure = cwd / "structure.json"
            drafts = cwd / "drafts"
            write_structure(structure, min_chars=5, proposition_count=2)
            target = wb_main.BookTarget(structure_path=structure, drafts_dir=drafts)
            loaded = wb_main.load_structure(structure)
            items = wb_main.work_items(target, loaded)
            for item in items:
                wb_main.ensure_draft(item, 2)
            items[0].path.write_text(
                items[0].path.read_text(encoding="utf-8") + "\nfirst body",
                encoding="utf-8",
            )
            env = {"XDG_CONFIG_HOME": str(cwd / "xdg")}

            preset_result = run_wb(
                "preset",
                "save",
                "small",
                "structure",
                str(structure),
                "drafts",
                str(drafts),
                cwd=cwd,
                env=env,
            )
            status_result = run_wb("use", "small", "status", cwd=cwd, env=env)

        self.assertEqual(preset_result.returncode, 0)
        self.assertEqual(status_result.returncode, 0)
        self.assertIn("progress : 1/2 (50%)", status_result.stdout)
        self.assertIn("next     : One / 2", status_result.stdout)
        self.assertIn("chars    : 0/5", status_result.stdout)

    def test_write_stops_after_single_editor_pass_when_still_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            structure = cwd / "structure.json"
            drafts = cwd / "drafts"
            write_structure(structure, min_chars=20)
            editor = cwd / "editor.sh"
            editor.write_text("#!/usr/bin/env bash\nprintf 'short' >> \"$1\"\n", encoding="utf-8")
            editor.chmod(0o755)
            env = {
                "XDG_CONFIG_HOME": str(cwd / "xdg"),
                "EDITOR": str(editor),
                "VISUAL": "",
            }

            result = run_wb("write", str(structure), "drafts", str(drafts), cwd=cwd, env=env)

        self.assertEqual(result.returncode, 1)
        self.assertIn("incomplete 5/20", result.stdout)

    def test_scaffold_lines_remain_wrapped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            item = wb_main.WorkItem(
                chapter_index=0,
                proposition_index=1,
                chapter_title="One",
                proposition=(
                    "This proposition is long enough to require wrapping before it is "
                    "written into the generated Markdown scaffold."
                ),
                path=Path(tmp) / "draft.md",
                min_chars=1,
            )

            text = wb_main.draft_scaffold(item, 1)

        self.assertIn("# One", text)
        self.assertEqual(
            [(i, len(line)) for i, line in enumerate(text.splitlines(), start=1) if len(line) > 79],
            [],
        )


if __name__ == "__main__":
    unittest.main()
