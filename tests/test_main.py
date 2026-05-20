from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
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


class MainTests(unittest.TestCase):
    def test_help_and_version_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {"XDG_CONFIG_HOME": str(Path(tmp) / "config")}

            help_result = run_wb("-h", cwd=ROOT, env=env)
            version_result = run_wb("-v", cwd=ROOT, env=env)

        self.assertEqual(help_result.returncode, 0)
        self.assertIn("Writer's Block", help_result.stdout)
        self.assertIn("flags:", help_result.stdout)
        self.assertIn("features:", help_result.stdout)
        self.assertIn("wb -u", help_result.stdout)
        self.assertNotIn("usage:", help_result.stdout)
        self.assertNotIn("--help", help_result.stdout)
        self.assertEqual(version_result.stdout, "0.0.0\n")

    def test_conf_creates_xdg_app_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            env = {"XDG_CONFIG_HOME": str(xdg), "EDITOR": "true", "VISUAL": ""}

            result = run_wb("conf", cwd=ROOT, env=env)
            config_path = xdg / "wb" / "config.json"

            self.assertEqual(result.returncode, 0)
            self.assertTrue(config_path.exists())
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["book_config"], "wb.json")
            self.assertEqual(config["min_chars"], 500)
            self.assertEqual(config["quality_gate"]["threshold"], 3)

    def test_init_and_status_use_cwd_book_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            env = {"XDG_CONFIG_HOME": str(cwd / "xdg")}

            init_result = run_wb("init", cwd=cwd, env=env)
            status_result = run_wb("st", cwd=cwd, env=env)

        self.assertEqual(init_result.returncode, 0)
        self.assertEqual(status_result.returncode, 0)
        self.assertIn("Untitled Book", status_result.stdout)
        self.assertIn("progress : 0/1", status_result.stdout)
        self.assertIn("config   : wb.json", status_result.stdout)

    def test_write_counts_only_below_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config = cwd / "book.json"
            config.write_text(
                textwrap.dedent(
                    """\
                    {
                      "title": "Small",
                      "settings": {
                        "draft_dir": "drafts",
                        "min_chars": 1,
                        "quality_gate": {"enabled": false}
                      },
                      "chapters": [
                        {"title": "One", "propositions": ["Argue one thing."]}
                      ]
                    }
                    """
                ),
                encoding="utf-8",
            )
            editor = cwd / "editor.sh"
            editor.write_text("#!/usr/bin/env bash\nprintf 'x' >> \"$1\"\n", encoding="utf-8")
            editor.chmod(0o755)
            env = {
                "XDG_CONFIG_HOME": str(cwd / "xdg"),
                "EDITOR": str(editor),
                "VISUAL": "",
            }

            result = run_wb("w", "-1", "-c", str(config), cwd=cwd, env=env)
            draft = cwd / "drafts" / "00-one" / "01.md"

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
            self.assertIn("done", result.stdout)

    def test_openai_transport_errors_are_reported_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            draft = Path(tmp) / "draft.md"
            draft.write_text(
                f"{wb_main.DRAFT_MARKER}\nplain draft body\n",
                encoding="utf-8",
            )
            item = wb_main.WorkItem(
                chapter_index=0,
                proposition_index=1,
                chapter_title="One",
                proposition="Argue one thing.",
                path=draft,
                min_chars=1,
            )

            original_key = wb_main.openai_api_key_from_bashrc
            original_urlopen = wb_main.urllib.request.urlopen
            wb_main.openai_api_key_from_bashrc = lambda: "test-key"
            wb_main.urllib.request.urlopen = lambda *args, **kwargs: (_ for _ in ()).throw(
                LookupError("unknown encoding: idna")
            )
            stderr = io.StringIO()
            try:
                with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(stderr):
                    wb_main.score_with_openai(item, {"settings": {"quality_gate": {"threshold": 3}}})
            finally:
                wb_main.openai_api_key_from_bashrc = original_key
                wb_main.urllib.request.urlopen = original_urlopen

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("OpenAI scoring failed: unknown encoding: idna", stderr.getvalue())
            self.assertIn("encodings.idna", sys.modules)

    def test_score_pass_uses_numeric_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            draft = Path(tmp) / "draft.md"
            draft.write_text(
                f"{wb_main.DRAFT_MARKER}\nplain draft body\n",
                encoding="utf-8",
            )
            item = wb_main.WorkItem(
                chapter_index=0,
                proposition_index=1,
                chapter_title="One",
                proposition="Argue one thing.",
                path=draft,
                min_chars=1,
            )

            original_request = wb_main.openai_json_request
            wb_main.openai_json_request = (
                lambda payload, label: {
                    "score": 4,
                    "pass": False,
                    "reasons": [],
                    "revision_targets": [],
                }
            )
            try:
                score = wb_main.score_with_openai(
                    item,
                    {"settings": {"quality_gate": {"threshold": 3}}},
                )
            finally:
                wb_main.openai_json_request = original_request

        self.assertTrue(score["pass"])
        self.assertEqual(score["threshold"], 3)

    def test_lowered_threshold_can_complete_existing_score_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config = cwd / "book.json"
            config.write_text(
                textwrap.dedent(
                    """\
                    {
                      "title": "Small",
                      "settings": {
                        "draft_dir": "drafts",
                        "min_chars": 1,
                        "quality_gate": {"enabled": true, "threshold": 3}
                      },
                      "chapters": [
                        {"title": "One", "propositions": ["Argue one thing."]}
                      ]
                    }
                    """
                ),
                encoding="utf-8",
            )
            book_config = wb_main.load_book_config(config)
            item = wb_main.work_items(config, book_config)[0]
            wb_main.ensure_draft(item, 1)
            item.path.write_text(
                item.path.read_text(encoding="utf-8") + "\nplain body",
                encoding="utf-8",
            )
            wb_main.write_state(
                item,
                config,
                book_config,
                {
                    "body_hash": wb_main.body_hash(item.path),
                    "pass": False,
                    "score": 4,
                    "threshold": 5,
                },
            )

            complete = wb_main.item_complete(item, config, book_config)

        self.assertTrue(complete)

    def test_failed_gate_blocks_after_single_editor_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config = cwd / "book.json"
            config.write_text(
                textwrap.dedent(
                    """\
                    {
                      "title": "Small",
                      "settings": {
                        "draft_dir": "drafts",
                        "min_chars": 1,
                        "quality_gate": {"enabled": true, "threshold": 3}
                      },
                      "chapters": [
                        {"title": "One", "propositions": ["Argue one thing."]}
                      ]
                    }
                    """
                ),
                encoding="utf-8",
            )
            opens: list[Path] = []

            def fake_editor(path: Path) -> int:
                opens.append(path)
                path.write_text(
                    path.read_text(encoding="utf-8") + "\nfirst body",
                    encoding="utf-8",
                )
                return 0

            original_editor = wb_main.open_editor
            original_score = wb_main.score_with_openai
            wb_main.open_editor = fake_editor
            wb_main.score_with_openai = (
                lambda item, book_config: {
                    "score": 2,
                    "pass": False,
                    "reasons": ["too wordy"],
                    "revision_targets": ["cut"],
                }
            )
            stdout = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout):
                    result = wb_main.command_write(config, ["-1"])
            finally:
                wb_main.open_editor = original_editor
                wb_main.score_with_openai = original_score

            output = stdout.getvalue()

        self.assertEqual(result, 1)
        self.assertEqual(len(opens), 1)
        self.assertIn("blocked  : revise this proposition before moving on", output)

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
