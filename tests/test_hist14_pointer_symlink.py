"""HIST-14: an active history pointer must not silently vanish via symlink."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from backend.historical_activation import ErroAtivacaoHistorica, carregar_historico_ativo


class HistoricalPointerSymlinkTests(TestCase):
    def test_absent_pointer_still_means_no_active_history(self):
        with TemporaryDirectory() as root:
            self.assertIsNone(carregar_historico_ativo(root))

    def test_broken_symlink_cannot_be_mistaken_for_no_history(self):
        with TemporaryDirectory() as root:
            pointer = Path(root) / "evidencias" / "historico-ativo.json"
            pointer.parent.mkdir()
            try:
                pointer.symlink_to("missing-active-history.json")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"OS does not allow symlink creation: {exc}")
            self.assertFalse(pointer.exists())
            self.assertTrue(pointer.is_symlink())
            with self.assertRaisesRegex(ErroAtivacaoHistorica, "link simbólico"):
                carregar_historico_ativo(root)

    def test_symlink_rejected_even_when_target_exists(self):
        with TemporaryDirectory() as root:
            pointer = Path(root) / "evidencias" / "historico-ativo.json"
            pointer.parent.mkdir()
            (pointer.parent / "other.json").write_text("{}", encoding="utf-8")
            try:
                pointer.symlink_to("other.json")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"OS does not allow symlink creation: {exc}")
            with self.assertRaisesRegex(ErroAtivacaoHistorica, "link simbólico"):
                carregar_historico_ativo(root)

    def test_pointer_symlink_policy_on_windows_without_symlink_privileges(self):
        with TemporaryDirectory() as root:
            pointer = Path(root) / "evidencias" / "historico-ativo.json"
            real_is_symlink = Path.is_symlink

            def simulate_pointer_symlink(path):
                return path == pointer or real_is_symlink(path)

            with patch.object(Path, "is_symlink", simulate_pointer_symlink):
                with self.assertRaisesRegex(ErroAtivacaoHistorica, "link simbólico"):
                    carregar_historico_ativo(root)
