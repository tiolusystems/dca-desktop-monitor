"""Regressions: 2021–2026 file SHA and SQLite checks never block Tk."""
import ast
from pathlib import Path
import threading
import unittest

def _refresh_function(loader):
    """Execute the actual UI method without importing optional Tk packages.

    The minimal finance CI intentionally has no customtkinter installed.
    """
    source = Path(__file__).resolve().parents[1] / "gui" / "janela_historico.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "JanelaHistorico")
    method = next(n for n in cls.body
                  if isinstance(n, ast.FunctionDef) and n.name == "recarregar")
    scope = {
        "carregar_historico_ativo": loader,
        "TEXT_SECONDARY": "#cccccc", "NEON_RED": "#ff0000",
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(source), "exec"), scope)
    return scope["recarregar"]


class _Queue:
    def __init__(self):
        self.worker = None
        self.done = None

    def run(self, fn):
        self.worker = fn

    def post(self, fn):
        self.done = fn


class _Label:
    def __init__(self):
        self.last = {}

    def configure(self, **kwargs):
        self.last = kwargs


class _FakeHistorico:
    _busy = False
    _data_dir = Path("/nao-abrir-dados-operacionais")
    _origem = None
    _painel = None

    def __init__(self):
        self._tasks = _Queue()
        self.status = _Label()
        self.summary = _Label()
        self.busy_calls = []
        self.messages = []

    def _ocupar(self, msg):
        self.busy_calls.append(msg)

    def _liberar(self):
        self.busy_calls.append("liberado")

    def _escrever(self, text):
        self.messages.append(text)

    def winfo_exists(self):
        return True


class HistoricalAsyncUITests(unittest.TestCase):
    def test_refresh_does_not_read_csv_or_sqlite_on_ui_thread(self):
        dummy = _FakeHistorico()
        seen = []
        owner = threading.get_ident()

        def load(_):
            seen.append(threading.get_ident())
            return None

        _refresh_function(load)(dummy)
        self.assertEqual(seen, [], "I/O executado no thread Tk")
        self.assertIsNotNone(dummy._tasks.worker)
        thread = threading.Thread(target=dummy._tasks.worker)
        thread.start()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(seen), 1)
        self.assertNotEqual(seen[0], owner)
        self.assertIsNotNone(dummy._tasks.done)
        dummy._tasks.done()
        self.assertIn("ainda não ativado", dummy.status.last["text"])
        self.assertEqual(dummy.busy_calls[-1], "liberado")

    def test_integrity_error_clears_previous_valuation(self):
        dummy = _FakeHistorico()
        dummy._painel = {"subtotal_avaliavel_brl": "999999"}
        dummy._origem = Path("/arquivo/antigo")
        def falha(_):
            raise ValueError("integridade recusada")

        _refresh_function(falha)(dummy)
        thread = threading.Thread(target=dummy._tasks.worker)
        thread.start()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        dummy._tasks.done()
        self.assertIsNone(dummy._painel)
        self.assertIsNone(dummy._origem)
        self.assertIn("integridade recusada", dummy.status.last["text"])
        self.assertIn("integridade", dummy.summary.last["text"])


if __name__ == "__main__":
    unittest.main()
