"""Separate documentary SQLite integration, provenance and protection of operational data."""
import csv
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.historical_evidence import COLUNAS
from backend.historical_store import (
    ErroLivroDocumental, construir_livro_documental,
)


def transacao():
    row={field:"" for field in COLUNAS}
    row.update({
        "data_hora":"2025-05-02 10:00:00",
        "fonte":"BINANCE_TRANSACOES",
        "arquivo_fonte_sha256":"b"*64,
        "linha_fonte":"2","classe_evidencia":"MOVIMENTO_EXTERNO",
        "impacto_saldo":"SIM_APENAS_SALDO_CONTA_DOCUMENTADA",
        "conta":"Spot","operacao_origem":"Deposit",
        "ativo":"BTC","quantidade_assinada":"0.04",
        "custo_aquisicao":"NAO_DETERMINADO_POR_ESTE_EVENTO",
    })
    assinatura=(f'{row["fonte"]}:{row["arquivo_fonte_sha256"]}:'
               f'{row["linha_fonte"]}:{row["classe_evidencia"]}:{row["data_hora"]}')
    row["id_evento"]=sha256(assinatura.encode()).hexdigest()[:24]
    return row


class LivroDocumentalTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.csv=self.root/"fonte.csv"
        self.data=self.root/"dados"
        self.data.mkdir()
        with self.csv.open("w",encoding="utf-8-sig",newline="") as fp:
            w=csv.DictWriter(fp,fieldnames=COLUNAS)
            w.writeheader()
            w.writerow(transacao())

    def test_criar_reabrir_e_idempotente_sem_modificar_original(self):
        financeiro=self.data/"portfolio.sqlite3"
        # Sentinela: jamais deve ser aberta como banco ou modificada.
        financeiro.write_bytes(b"BANCO-FINANCEIRO-INTACTO")
        r=construir_livro_documental(self.csv,self.data)
        livro=Path(r["arquivo"])
        self.assertEqual(financeiro.read_bytes(),b"BANCO-FINANCEIRO-INTACTO")
        self.assertFalse(r["sqlite_financeiro_alterado"])
        self.assertEqual(r["eventos"],1)
        with closing(sqlite3.connect(livro.resolve().as_uri()+"?mode=ro",uri=True)) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM eventos").fetchone()[0],1)
            stored=db.execute("SELECT payload_json FROM eventos").fetchone()[0]
            self.assertEqual(json.loads(stored)["quantidade_assinada"],"0.04")
            self.assertEqual(db.execute("SELECT custo_brl FROM saldos_documentais").fetchone()[0],None)
        before=livro.read_bytes()
        again=construir_livro_documental(self.csv,self.data)
        self.assertTrue(again["ja_existia"])
        self.assertEqual(livro.read_bytes(),before)
        self.assertEqual(financeiro.read_bytes(),b"BANCO-FINANCEIRO-INTACTO")

    def test_csv_corrompido_nega_novo_banco(self):
        self.csv.write_text("Data,Moeda,Operacao\n2025-05-01,BTC,compra\n",encoding="utf-8")
        with self.assertRaises(ValueError):
            construir_livro_documental(self.csv,self.data)
        self.assertFalse((self.data/"evidencias").exists())

    def test_nao_substituir_livro_existente_corrompido(self):
        r=construir_livro_documental(self.csv,self.data)
        livro=Path(r["arquivo"])
        livro.write_bytes(b"CORRUPTO")
        with self.assertRaisesRegex(ErroLivroDocumental,"inválido"):
            construir_livro_documental(self.csv,self.data)
        self.assertEqual(livro.read_bytes(),b"CORRUPTO")


if __name__=="__main__":
    unittest.main()
