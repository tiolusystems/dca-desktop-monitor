"""NC-02: metadata modified during quotes/callback/export must block display."""
import csv
import json
import sqlite3
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from backend.historical_activation import ativar_historico_documental
from backend.historical_evidence import COLUNAS
from backend.historical_snapshot_guard import (
    abrir_snapshot_documental, revalidar_snapshot_rapido,
    HistoricoMudouDuranteConsulta,
)


def row(n):
    x={k:"" for k in COLUNAS}
    x.update({
        "data_hora": f"2026-01-01 10:00:{n:02d}",
        "fonte": "BINANCE_TRANSACOES", "arquivo_fonte_sha256":"d"*64,
        "linha_fonte": str(n+2), "classe_evidencia": "MOVIMENTO_EXTERNO",
        "impacto_saldo": "SIM_APENAS_SALDO_CONTA_DOCUMENTADA",
        "conta": "Spot", "operacao_origem": "Deposit",
        "ativo": "BTC", "quantidade_assinada":"0.02",
        "custo_aquisicao": "NAO_DETERMINADO_POR_ESTE_EVENTO",
    })
    raw=f'{x["fonte"]}:{x["arquivo_fonte_sha256"]}:{x["linha_fonte"]}:{x["classe_evidencia"]}:{x["data_hora"]}'
    x["id_evento"]=sha256(raw.encode()).hexdigest()[:24]
    return x


class DocumentSnapshotGuardTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.data=self.root/"wallet"
        self.data.mkdir()
        self.wallet=self.data/"portfolio.sqlite3"
        self.wallet.write_bytes(b"PORTFOLIO_ORIGINAL_INTATO")
        self.original=self.root/"hist.csv"
        with self.original.open("w",encoding="utf-8-sig",newline="") as fp:
            w=csv.DictWriter(fp,fieldnames=COLUNAS)
            w.writeheader()
            w.writerows([row(1)])
        self.imported=ativar_historico_documental(
            self.original,self.data,
            sha_confirmado=sha256(self.original.read_bytes()).hexdigest())
        self.source=Path(self.imported["arquivo_ativo"])
        self.snapshot=abrir_snapshot_documental(self.data,self.source)

    def test_source_valid_callback_and_original_wallet_untouched(self):
        self.assertTrue(revalidar_snapshot_rapido(self.data,self.snapshot))
        self.assertEqual(self.wallet.read_bytes(),b"PORTFOLIO_ORIGINAL_INTATO")

    def test_manifest_changed_during_network_invalidates_callback(self):
        meta=self.source.with_suffix(".json")
        payload=json.loads(meta.read_text("utf-8"))
        payload["quantidade"]=999
        meta.write_text(json.dumps(payload),encoding="utf-8")
        with self.assertRaises(HistoricoMudouDuranteConsulta):
            revalidar_snapshot_rapido(self.data,self.snapshot)
        self.assertEqual(self.wallet.read_bytes(),b"PORTFOLIO_ORIGINAL_INTATO")

    def test_pointer_changed_in_pending_ui_callback(self):
        pointer=self.data/"evidencias"/"historico-ativo.json"
        old=json.loads(pointer.read_text("utf-8"))
        old["eventos"]=999
        pointer.write_text(json.dumps(old),encoding="utf-8")
        with self.assertRaises(HistoricoMudouDuranteConsulta):
            revalidar_snapshot_rapido(self.data,self.snapshot)

    def test_sqlite_change_during_callback_detected(self):
        with sqlite3.connect(self.imported["livro"]) as db:
            db.execute("UPDATE saldos_documentais SET saldo_algebrico='999'")
            db.commit()
        with self.assertRaises(HistoricoMudouDuranteConsulta):
            revalidar_snapshot_rapido(self.data,self.snapshot)

    def test_source_change_in_callback_detected(self):
        self.source.write_bytes(b"alterado")
        with self.assertRaises(HistoricoMudouDuranteConsulta):
            revalidar_snapshot_rapido(self.data,self.snapshot)

    def test_stale_generation_after_second_historical_activation(self):
        other=self.root/"outro.csv"
        with other.open("w",encoding="utf-8-sig",newline="") as fp:
            w=csv.DictWriter(fp,fieldnames=COLUNAS)
            w.writeheader()
            w.writerows([row(1),row(2)])
        ativar_historico_documental(
            other,self.data,sha_confirmado=sha256(other.read_bytes()).hexdigest())
        with self.assertRaises(HistoricoMudouDuranteConsulta):
            revalidar_snapshot_rapido(self.data,self.snapshot)


if __name__=="__main__":
    unittest.main()
