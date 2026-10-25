"""Regressions: 2021–2026 file SHA and SQLite checks never block Tk."""
import ast
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from pathlib import Path
import threading
import unittest

def _refresh_function(loader, *, snapshot=None, guard=None, monitor=None):
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
        "abrir_snapshot_documental": snapshot or (lambda *_: {"marcas": ("ok",)}),
        "revalidar_snapshot_rapido": guard or (lambda *_: True),
        "HistoricoMudouDuranteConsulta": ValueError,
        "calcular_painel_documental": monitor or (
            lambda *args, **kwargs: {"subtotal_avaliavel_brl": "250000"}
        ),
        "Decimal": Decimal, "datetime": datetime, "timezone": timezone,
        "TEXT_SECONDARY": "#cccccc", "NEON_RED": "#ff0000",
        "CYAN": "#00ffff",
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

    def _exibir(self, report):
        self.messages.append(("RENDERED", report))


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


    def test_manifest_tampered_while_fetching_quotes_never_publishes_values(self):
        dummy = _FakeHistorico()
        dummy._painel = {"subtotal_avaliavel_brl": "100000"}
        state = {"tampered": False}
        def stamp(*_):
            if state["tampered"]:
                raise ValueError("manifesto adulterado durante rede")
            return {"marcas": ("original",)}
        def quotes(*_):
            state["tampered"] = True
            return {"BTC": 100000}, 5, []
        src=Path("/fonte-documental-comprovada.csv")
        refresh = _refresh_function(
            lambda _: src, snapshot=stamp,
            monitor=lambda *args, **kw: {"subtotal_avaliavel_brl": "250000"})
        with patch("backend.historical_reconciliation.reconciliar_historico_documental",
                   return_value={"saldos": [{"ativo": "BTC",
                                             "saldo_algebrico": "0.1"}]}), patch(
                "backend.historical_quotes.consultar_cotacoes_historicas",
                side_effect=quotes):
            refresh(dummy)
            dummy._tasks.worker()
            dummy._tasks.done()
        self.assertIsNone(dummy._painel)
        self.assertFalse(any(isinstance(m,tuple) and m[0]=="RENDERED"
                             for m in dummy.messages))
        self.assertIn("manifesto adulterado", dummy.status.last["text"])

    def test_manifest_tampered_while_callback_waits_never_publishes_values(self):
        dummy = _FakeHistorico()
        state = {"tampered": False}
        def guard(*_):
            if state["tampered"]:
                raise ValueError("manifesto modificado na fila Tk")
        refresh = _refresh_function(
            lambda _: Path("/fonte-documental-comprovada.csv"),
            snapshot=lambda *_: {"marcas": ("original",)}, guard=guard,
            monitor=lambda *args, **kw: {"subtotal_avaliavel_brl": "250000"})
        with patch("backend.historical_reconciliation.reconciliar_historico_documental",
                   return_value={"saldos": [{"ativo": "BTC",
                                             "saldo_algebrico": "0.1"}]}), patch(
                "backend.historical_quotes.consultar_cotacoes_historicas",
                return_value=({"BTC": 100000}, 5, [])):
            refresh(dummy)
            dummy._tasks.worker()
            state["tampered"] = True
            dummy._tasks.done()
        self.assertIsNone(dummy._painel)
        self.assertFalse(any(isinstance(m,tuple) and m[0]=="RENDERED"
                             for m in dummy.messages))
        self.assertIn("manifesto modificado", dummy.status.last["text"])


if __name__ == "__main__":
    unittest.main()
