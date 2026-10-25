"""Offline contract: publish v1.0.3 to the same repository the app polls."""
from pathlib import Path
import unittest

from backend.app_lifecycle import APP_VERSION, RELEASE_ENDPOINT
from scripts.release_archive import archive_name


ROOT = Path(__file__).resolve().parents[1]
RELEASE_REPO = "tiolusystems/dca-desktop-monitor"


class ReleaseChannelContractTests(unittest.TestCase):
    def test_version_and_release_channel_match_owned_repository(self):
        self.assertEqual(APP_VERSION, "1.0.3")
        self.assertEqual(
            RELEASE_ENDPOINT,
            f"https://api.github.com/repos/{RELEASE_REPO}/releases/latest",
        )

    def test_expected_portable_archives_are_versioned(self):
        self.assertEqual(archive_name("Windows"), "DCA-Monitor-v1.0.3-Windows-x64.zip")
        self.assertEqual(archive_name("Linux"), "DCA-Monitor-v1.0.3-Linux-x64.tar.gz")

    def test_release_workflow_requires_both_os_and_admin_gate(self):
        workflow = (ROOT / ".github/workflows/release-packages.yml").read_text(
            encoding="utf-8"
        )
        for expected in (
            "needs: [package-windows, package-linux]",
            "environment: production",
            "DCA_DISTRIBUTION_APPROVED_SHA",
            "git merge-base --is-ancestor",
            'test "$APPROVED_SHA" = "$GITHUB_SHA"',
            "sha256sum -c",
            'gh release create "$RELEASE_TAG"',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, workflow)


if __name__ == "__main__":
    unittest.main()
