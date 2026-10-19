"""Execute the actual publication gate against an isolated Git history.

These are code-level negative tests, not proof of GitHub administrative rules.
No credentials, tags, network services or releases are created.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseCommitGateTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "The publication gate runs on Ubuntu/bash")
    def test_actual_gate_accepts_only_approved_current_main_and_matching_version(self):
        workflow = (ROOT / ".github/workflows/release-packages.yml").read_text()
        marker = "      - name: Require canonical main ancestry and administrative SHA approval"
        step = workflow.split(marker, 1)[1].split("      - uses:", 1)[0]
        gate = textwrap.dedent(step.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory(prefix="dca-release-gate-") as temp:
            root = Path(temp)
            origin, checkout = root / "origin", root / "checkout"

            def git(*args, cwd=origin):
                return subprocess.check_output(
                    ["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
                ).strip()

            origin.mkdir()
            git("init", "-b", "main")
            git("config", "user.name", "Synthetic release gate test")
            git("config", "user.email", "gate@example.invalid")
            (origin / "backend").mkdir()
            (origin / "backend/app_lifecycle.py").write_text('APP_VERSION = "1.0.0"\n')
            git("add", ".")
            git("commit", "-m", "Synthetic ancestor")
            ancestor = git("rev-parse", "HEAD")
            (origin / "change.txt").write_text("Synthetic current main\n")
            git("add", ".")
            git("commit", "-m", "Synthetic current main")
            current = git("rev-parse", "HEAD")
            git("clone", str(origin), str(checkout), cwd=root)

            cases = (
                ("approved current main", current, current, "refs/tags/v1.0.0", True),
                ("missing approval", current, "", "refs/tags/v1.0.0", False),
                ("approval for another commit", current, ancestor, "refs/tags/v1.0.0", False),
                ("approved old ancestor", ancestor, ancestor, "refs/tags/v1.0.0", False),
                ("incorrect version tag", current, current, "refs/tags/v1.0.1", False),
                ("branch instead of version tag", current, current, "refs/heads/main", False),
            )
            for name, sha, approved, ref, accepted in cases:
                with self.subTest(case=name):
                    result = subprocess.run(
                        ["bash", "-c", gate], cwd=checkout,
                        env={**os.environ, "GITHUB_SHA": sha,
                             "APPROVED_SHA": approved, "GITHUB_REF": ref},
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode == 0, accepted, result.stderr)
