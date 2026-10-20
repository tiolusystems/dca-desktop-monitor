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
import json
import sys


ROOT = Path(__file__).resolve().parents[1]


class ReleaseCommitGateTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "The publication job runs on Ubuntu/bash")
    def test_publication_never_moves_tags_or_overwrites_a_release(self):
        workflow = (ROOT / ".github/workflows/release-packages.yml").read_text()
        step = workflow.split("      - name: Publish both OS builds only after approvals", 1)[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory(prefix="dca-publication-dry-run-") as temp:
            root = Path(temp)
            fake = root / "gh"
            fake.write_text("#!" + sys.executable + "\n" + textwrap.dedent('''\
                import json, os, pathlib, sys
                args = sys.argv[1:]
                state_path = pathlib.Path(os.environ['FAKE_STATE'])
                state = json.loads(state_path.read_text())
                state['calls'].append(args)
                status = 0
                if args[:2] == ['release', 'view']:
                    status = 0 if state['release'] else 1
                elif args[:3] == ['api', '--method', 'POST']:
                    assert 'ref=refs/tags/' + os.environ['EXPECTED_TAG'] in args
                    assert 'sha=' + os.environ['GITHUB_SHA'] in args
                    assert not state['tag']
                    state['tag'] = os.environ['GITHUB_SHA']
                elif args[0] == 'api':
                    if state.get('lookup_error'):
                        print(json.dumps({'message': 'Resource not accessible by integration'}))
                        print('gh: Resource not accessible by integration (HTTP 403)', file=sys.stderr)
                        status = 1
                    elif state['tag']: print(state['tag'])
                    else:
                        # gh emits the JSON error body on stdout even with --jq.
                        print(json.dumps({'message': 'Not Found', 'status': '404'}))
                        print('gh: Not Found (HTTP 404)', file=sys.stderr)
                        status = 1
                elif args[:2] == ['release', 'create']:
                    assert args[2] == os.environ['EXPECTED_TAG']
                    assert state['tag'] == os.environ['GITHUB_SHA']
                    assert not state['release']
                    state['release'] = True
                else: raise AssertionError(args)
                state_path.write_text(json.dumps(state))
                sys.exit(status)
            '''))
            fake.chmod(0o755)
            approved = "a" * 40
            cases = (
                ("manual new tag", "workflow_dispatch", "", False, True),
                ("manual same tag retry", "workflow_dispatch", approved, False, True),
                ("manual different tag target", "workflow_dispatch", "b" * 40, False, False),
                ("published release", "workflow_dispatch", approved, True, False),
                ("tag event matching SHA", "push", approved, False, True),
                ("tag event different SHA", "push", "b" * 40, False, False),
                ("lookup forbidden", "workflow_dispatch", "", False, False),
            )
            for name, event, tag, published, accepted in cases:
                with self.subTest(case=name):
                    state_path = root / "state.json"
                    state_path.write_text(json.dumps(dict(tag=tag, release=published, calls=[],
                        lookup_error=name == "lookup forbidden")))
                    result = subprocess.run(["bash", "-c", script], cwd=ROOT,
                        env={**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                             "FAKE_STATE": str(state_path), "EXPECTED_TAG": "v" + __import__("backend.app_lifecycle", fromlist=["APP_VERSION"]).APP_VERSION, "GITHUB_EVENT_NAME": event,
                             "GITHUB_SHA": approved, "GITHUB_REPOSITORY": "synthetic/repo"},
                        capture_output=True, text=True)
                    state = json.loads(state_path.read_text())
                    self.assertEqual(result.returncode == 0, accepted, result.stderr)
                    self.assertEqual(any(c[:2] == ['release', 'create'] for c in state['calls']), accepted)
                    if not accepted:
                        self.assertEqual(state['tag'], tag)
                        self.assertEqual(state['release'], published)
                        self.assertFalse(any(c[:3] == ['api', '--method', 'POST'] for c in state['calls']))

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
                ("approved tag", current, current, "refs/tags/v1.0.0", "push", True),
                ("missing approval", current, "", "refs/tags/v1.0.0", "push", False),
                ("approval for another commit", current, ancestor, "refs/tags/v1.0.0", "push", False),
                ("approved old ancestor", ancestor, ancestor, "refs/tags/v1.0.0", "push", False),
                ("incorrect version tag", current, current, "refs/tags/v1.0.1", "push", False),
                ("branch push cannot publish", current, current, "refs/heads/main", "push", False),
                ("manual approved main", current, current, "refs/heads/main", "workflow_dispatch", True),
                ("manual missing approval", current, "", "refs/heads/main", "workflow_dispatch", False),
                ("manual stale SHA", ancestor, ancestor, "refs/heads/main", "workflow_dispatch", False),
                ("manual other branch", current, current, "refs/heads/other", "workflow_dispatch", False),
            )
            for name, sha, approved, ref, event, accepted in cases:
                with self.subTest(case=name):
                    result = subprocess.run(
                        ["bash", "-c", gate], cwd=checkout,
                        env={**os.environ, "GITHUB_SHA": sha,
                             "APPROVED_SHA": approved, "GITHUB_REF": ref,
                             "GITHUB_EVENT_NAME": event},
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode == 0, accepted, result.stderr)
