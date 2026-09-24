"""Smoke checks for the tracked inversion CLI entry, without judging period results."""

import subprocess
import unittest
from pathlib import Path

import pipeline


class InversionEntryTests(unittest.TestCase):
    def test_estimate_period_script_is_present_and_speaks_protocol(self):
        script = pipeline.INVERSION_ENTRY
        self.assertTrue(script.is_file(), f"missing {script}")
        text = script.read_text(encoding="utf-8")
        self.assertIn("__PROGRESS__", text)
        self.assertIn("__SUMMARY__", text)
        self.assertIn("argparse", text)
        self.assertEqual(
            script,
            Path(__file__).resolve().parents[1] / "inversion" / "scripts" / "estimate_period.py",
        )

    def test_estimate_period_script_is_tracked_by_git(self):
        inversion_root = pipeline.INVERSION_ENTRY.parent.parent
        ignored = subprocess.run(
            [
                "git",
                "-C",
                str(inversion_root),
                "check-ignore",
                "-q",
                "scripts/estimate_period.py",
            ],
            check=False,
        )
        self.assertNotEqual(ignored.returncode, 0, "estimate_period.py 仍被 gitignore 忽略")
        listed = subprocess.run(
            [
                "git",
                "-C",
                str(inversion_root),
                "ls-files",
                "--error-unmatch",
                "scripts/estimate_period.py",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(listed.returncode, 0, listed.stderr or listed.stdout)
