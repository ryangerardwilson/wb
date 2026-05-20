from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WB = ROOT / "wb"


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
            self.assertIn("done", result.stdout)


if __name__ == "__main__":
    unittest.main()
