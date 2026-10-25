"""HIST-13: reject provenance tamper between pricing, UI publication and export."""
import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch


class _Queue:
    def __init__(self):
        self.worker=None
        self.done=None
    def run(self,fn):
        self.worker=fn
    def post(self,fn):
        self.done=fn

class _Label:
    def __init__(self):
        self.last={}
    def configure(self,**kw):
        self.last=kw

class _Gui:
    _busy=False
    _data_dir=Path("/fake-wallet")
    _origem=None
    _painel=None
    def __init__(self):
        self._tasks=_Queue()
        self.status=_Label()
        self.summary=_Label()
        self.msgs=[]
        self.shown=[]
    def _ocupar(self,*_):
        pass
    def _liberar(self):
        pass
    def _escrever(self,text):
        self.msgs.append(text)
    def _exibir(self,report):
        self.shown.append(report)
    def winfo_exists(self):
        return True

def _compile_method(name, loader):
    source=Path(__file__).resolve().parents[1]/"gui"/"janela_historico.py"
    tree=ast.parse(source.read_text(encoding="utf-8"))
    cls=next(c for c in tree.body if isinstance(c,ast.ClassDef)
             and c.name=="JanelaHistorico")
    method=next(m for m in cls.body if isinstance(m,ast.FunctionDef) and m.name==name)
    scope={
        "carregar_historico_ativo":loader,
        "calcular_painel_documental": lambda *a, **kw: {
            "subtotal_avaliavel_brl": "500000.0"},
        "Decimal":Decimal,"datetime":datetime,"timezone":timezone,"Path":Path,
        "NEON_RED":"red","CYAN":"cyan","TEXT_SECONDARY":"gray",
        "ErroAtivacaoHistorica":ValueError,
    }
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),"exec"),scope)
    return scope[name]

class Hist13RaceTests(unittest.TestCase):
    def _fixture(self):
        state={"revisions":0,"calls":0}
        def load(_):
            state["calls"]+=1
            if state["revisions"]:
                raise ValueError("manifesto alterado durante cotação")
            return Path("/fake-wallet/evidencias/historico-a.csv")
        # Dynamic import references from real refresh() method.
        b=types.ModuleType("backend.backend")
        class PriceManager:
            pass
        b.PriceManager=PriceManager
        r=types.ModuleType("backend.historical_reconciliation")
        r.reconciliar_historico_documental=lambda *_:{
            "saldos":[{"ativo":"BTC","saldo_algebrico":"1"}]}
        q=types.ModuleType("backend.historical_quotes")
        def quotes(*_args,**_kwargs):
            return {"BTC":"100000"},"5",[]
        q.consultar_cotacoes_historicas=quotes
        m=types.ModuleType("backend.historical_live_monitor")
        m.calcular_painel_documental=lambda *a,**kw:{
            "subtotal_avaliavel_brl":"500000.0"}
        fake=_Gui()
        return state,load,fake,{"backend.backend":b,
            "backend.historical_reconciliation":r,
            "backend.historical_quotes":q,
            "backend.historical_live_monitor":m}

    def test_manifest_modified_during_network_never_publishes(self):
        state,load,gui,mods=self._fixture()
        def altered_quotes(*args,**kw):
            state["revisions"]=1
            return {"BTC":"100000"},"5",[]
        mods["backend.historical_quotes"].consultar_cotacoes_historicas=altered_quotes
        with patch.dict(sys.modules,mods):
            _compile_method("recarregar",load)(gui)
            gui._tasks.worker()
            gui._tasks.done()
        self.assertEqual(gui.shown,[])
        self.assertIsNone(gui._painel)
        self.assertIn("manifesto alterado",gui.status.last["text"])

    def test_manifest_modified_before_ui_callback_never_publishes(self):
        state,load,gui,mods=self._fixture()
        with patch.dict(sys.modules,mods):
            _compile_method("recarregar",load)(gui)
            gui._tasks.worker()
            state["revisions"]=1
            gui._tasks.done()
        self.assertEqual(gui.shown,[])
        self.assertIsNone(gui._painel)
        self.assertIn("bloqueado por integridade",gui.status.last["text"])

    def test_untampered_ui_is_published(self):
        state,load,gui,mods=self._fixture()
        with patch.dict(sys.modules,mods):
            _compile_method("recarregar",load)(gui)
            gui._tasks.worker()
            gui._tasks.done()
        self.assertEqual(len(gui.shown),1)
        self.assertEqual(gui.shown[0]["subtotal_avaliavel_brl"],"500000.0")
        self.assertGreaterEqual(state["calls"],3)


if __name__=="__main__":
    unittest.main()
