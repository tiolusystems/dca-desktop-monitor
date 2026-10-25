"""Historical portfolio activation must keep the original wallet byte-for-byte."""
import csv
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.historical_evidence import COLUNAS
from backend.historical_activation import (
    ErroAtivacaoHistorica, ativar_historico_documental,
    carregar_historico_ativo,
)


def row(n, delta, ativo="BTC"):
    value={k:"" for k in COLUNAS}
    value.update({
        "data_hora": f"2026-01-01 10:00:{n:02d}",
        "fonte": "BINANCE_TRANSACOES",
        "arquivo_fonte_sha256": "c"*64,
        "linha_fonte": str(n + 2),
        "classe_evidencia": "MOVIMENTO_EXTERNO",
        "impacto_saldo": "SIM_APENAS_SALDO_CONTA_DOCUMENTADA",
        "conta": "Spot", "operacao_origem": "Deposit",
        "ativo": ativo, "quantidade_assinada": str(delta),
        "custo_aquisicao": "NAO_DETERMINADO_POR_ESTE_EVENTO",
    })
    identifier=(f'{value["fonte"]}:{value["arquivo_fonte_sha256"]}:'
                f'{value["linha_fonte"]}:{value["classe_evidencia"]}:{value["data_hora"]}')
    value["id_evento"]=sha256(identifier.encode()).hexdigest()[:24]
    return value


class HistoricalActivationTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.dados=self.root/"dados"
        self.dados.mkdir()
        self.csv=self.root/"historico.csv"
        self.wallet=self.dados/"portfolio.sqlite3"
        self.wallet.write_bytes(b"DCA-FINANCIRO-ORIGINAL-INTACTO")
        with self.csv.open("w",encoding="utf-8-sig",newline="") as fp:
            out=csv.DictWriter(fp,fieldnames=COLUNAS)
            out.writeheader()
            out.writerows([row(0,"0.5"),row(1,"0.1")])

    def test_activates_and_reopens_with_same_sha_without_wallet_mutation(self):
        original=self.wallet.read_bytes()
        self.assertIsNone(carregar_historico_ativo(self.dados))
        digest=sha256(self.csv.read_bytes()).hexdigest()
        result=ativar_historico_documental(
            self.csv,self.dados,sha_confirmado=digest)
        self.assertEqual(result["eventos"],2)
        self.assertEqual(result["sha256"],digest)
        self.assertFalse(result["sqlite_operacional_alterado"])
        self.assertEqual(self.wallet.read_bytes(),original)
        ativo=carregar_historico_ativo(self.dados)
        self.assertEqual(ativo.read_bytes(),self.csv.read_bytes())
        with sqlite3.connect(result["livro"]) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM eventos").fetchone()[0],2)
            self.assertEqual(db.execute(
                "SELECT custo_brl FROM saldos_documentais").fetchone()[0],None)
        again=ativar_historico_documental(
            self.csv,self.dados,sha_confirmado=digest)
        self.assertEqual(again["sha256"],digest)
        self.assertEqual(carregar_historico_ativo(self.dados),ativo)
        self.assertEqual(self.wallet.read_bytes(),original)

    def test_rejects_changed_source_prior_to_activation(self):
        with self.assertRaisesRegex(ErroAtivacaoHistorica,"mudou"):
            ativar_historico_documental(
                self.csv,self.dados,sha_confirmado="a"*64)
        self.assertIsNone(carregar_historico_ativo(self.dados))
        self.assertEqual(self.wallet.read_bytes(),b"DCA-FINANCIRO-ORIGINAL-INTACTO")

    def test_tampered_archive_fails_closed(self):
        result=ativar_historico_documental(
            self.csv,self.dados,
            sha_confirmado=sha256(self.csv.read_bytes()).hexdigest())
        arquivo=Path(result["arquivo_ativo"])
        arquivo.write_bytes(b"alterado")
        with self.assertRaisesRegex(ErroAtivacaoHistorica,"modificado"):
            carregar_historico_ativo(self.dados)
        self.assertEqual(self.wallet.read_bytes(),b"DCA-FINANCIRO-ORIGINAL-INTACTO")

    def test_corrupt_separate_sqlite_blocks_source(self):
        result=ativar_historico_documental(
            self.csv,self.dados,
            sha_confirmado=sha256(self.csv.read_bytes()).hexdigest())
        Path(result["livro"]).write_bytes(b"ruim")
        with self.assertRaisesRegex(ErroAtivacaoHistorica,"integridade"):
            carregar_historico_ativo(self.dados)
        self.assertEqual(self.wallet.read_bytes(),b"DCA-FINANCIRO-ORIGINAL-INTACTO")

    def test_history_activation_is_independent_of_existing_wallet_contents(self):
        self.wallet.unlink()
        conn=sqlite3.connect(self.wallet)
        conn.execute("CREATE TABLE importante (id integer primary key, nota text)")
        conn.execute("INSERT INTO importante(nota) VALUES ('NÃO EDITAR')")
        conn.commit()
        conn.close()
        original=self.wallet.read_bytes()
        result=ativar_historico_documental(
            self.csv,self.dados,
            sha_confirmado=sha256(self.csv.read_bytes()).hexdigest())
        self.assertEqual(self.wallet.read_bytes(),original)
        self.assertTrue(Path(result["livro"]).is_file())


if __name__ == "__main__":
    unittest.main()
