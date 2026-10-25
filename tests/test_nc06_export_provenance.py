"""NC-06: exported documentary reports must be reproducible and exclusive."""
import ast
import csv
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile
from unittest.mock import Mock, patch
import unittest



def ui_export(guard, picker, reporter):
    path=Path(__file__).resolve().parents[1]/"gui"/"janela_historico.py"
    parsed=ast.parse(path.read_text("utf-8"))
    cls=next(x for x in parsed.body if isinstance(x,ast.ClassDef)
             and x.name=="JanelaHistorico")
    func=next(x for x in cls.body if isinstance(x,ast.FunctionDef)
              and x.name=="exportar")
    scope={
        "filedialog":Mock(asksaveasfilename=picker),
        "messagebox":reporter,
        "ErroAtivacaoHistorica":ValueError,
        "carregar_historico_ativo":guard,
        "Path":Path,"csv":csv,"json":json,"os":os,"tempfile":tempfile,
        "NEON_RED":"red",
    }
    exec(compile(ast.Module(body=[func],type_ignores=[]),str(path),"exec"),scope)
    return scope["exportar"]


class Fake:
    def __init__(self,root):
        self._busy=False
        self._data_dir=root
        self._origem=root/"origem.csv"
        self.status=Mock()
        self.summary=Mock()
        self.table=Mock()
        self._escrever=Mock()
        self._painel={
            "fonte_sha256":"a"*64,
            "instante_cotacoes_utc":"2026-10-25T10:15:00+00:00",
            "cambio_atual_usdt_brl":"5.03",
            "ativos":[{
                "ativo":"BTC","quantidade_documental":"0.5",
                "custodias":{"BINANCE:Spot":"0.5"},
                "valor_usdt":"45000","valor_brl":"226350",
                "estado":"VALOR_DOCUMENTAL",
                "pendencias_custodia":[],"lacuna_temporal":False,
                "custo_historico_brl":None,"lucro_prejuizo_brl":None,
                "compras_brutas_brl_binance":"0",
                "vendas_brutas_brl_binance":"0",
                "compras_brutas_brl_mp_transcricao":"0",
                "vendas_brutas_brl_mp_transcricao":"0",
            }],
        }

    def winfo_toplevel(self):
        return self


class ExportProvenanceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.fake=Fake(self.root)
        self.file=self.root/"NAO-IMPORTAR.csv"
        self.reporter=Mock()

    def test_report_includes_sha_app_version_clock_and_real_quote(self):
        fn=ui_export(lambda *_:self.fake._origem,lambda **kwargs:str(self.file),self.reporter)
        fn(self.fake)
        with self.file.open(encoding="utf-8-sig",newline="") as fp:
            rows=list(csv.DictReader(fp))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["fonte_sha256"],"a"*64)
        self.assertEqual(rows[0]["instante_cotacoes_utc"],"2026-10-25T10:15:00+00:00")
        self.assertEqual(rows[0]["cambio_usdt_brl_atual"],"5.03")
        self.assertEqual(rows[0]["tipo_relatorio"],"SNAPSHOT_DOCUMENTAL_NAO_CERTIFICADO_NAO_IMPORTAR")
        self.assertEqual(rows[0]["custodias"],'{"BINANCE:Spot": "0.5"}')
        self.assertIsNotNone(rows[0]["versao_aplicativo"])
        self.reporter.showerror.assert_not_called()

    def test_edit_after_save_dialog_blocks_report_and_removes_stale_ui(self):
        calls=[0]
        def guard(*_):
            calls[0]+=1
            if calls[0]>=2:
                raise ValueError("alteração do manifesto")
            return self.fake._origem
        fn=ui_export(guard,lambda **kwargs:str(self.file),self.reporter)
        fn(self.fake)
        self.assertFalse(self.file.exists())
        self.assertIsNone(self.fake._painel)
        self.fake._escrever.assert_called_once()
        self.reporter.showerror.assert_called_once()

    def test_existing_csv_is_not_overwritten(self):
        self.file.write_text("OUTRO RELATORIO",encoding="utf-8")
        fn=ui_export(lambda *_:True,lambda **kwargs:str(self.file),self.reporter)
        fn(self.fake)
        self.assertEqual(self.file.read_text("utf-8"),"OUTRO RELATORIO")
        self.reporter.showerror.assert_called_once()


if __name__=="__main__":
    unittest.main()
