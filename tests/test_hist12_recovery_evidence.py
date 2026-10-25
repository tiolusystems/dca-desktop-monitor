"""HIST-12: portable recovery must restore active evidence, not just old wallet."""
from contextlib import closing
import csv
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
import zipfile

from backend.backend import DataManager
from backend.historical_activation import (
    ativar_historico_documental, carregar_historico_ativo,
)
from backend.historical_evidence import COLUNAS
from backend.recovery_bundle import exportar_pacote, recuperar_pacote


def _evento(n, quantidade):
    row={key:"" for key in COLUNAS}
    row.update({
        "data_hora":f"2026-01-01 10:00:{n:02d}",
        "fonte":"BINANCE_TRANSACOES",
        "arquivo_fonte_sha256":"c"*64,
        "linha_fonte":str(n+2),
        "classe_evidencia":"MOVIMENTO_EXTERNO",
        "impacto_saldo":"SIM_APENAS_SALDO_CONTA_DOCUMENTADA",
        "conta":"Spot",
        "operacao_origem":"Deposit",
        "ativo":"BTC",
        "quantidade_assinada":quantidade,
        "custo_aquisicao":"NAO_DETERMINADO_POR_ESTE_EVENTO",
    })
    raw=(f'{row["fonte"]}:{row["arquivo_fonte_sha256"]}:'
         f'{row["linha_fonte"]}:{row["classe_evidencia"]}:{row["data_hora"]}')
    row["id_evento"]=sha256(raw.encode()).hexdigest()[:24]
    return row


class HistoricoRecoveryBundleTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.source=self.root/"wallet"
        self.dm=DataManager(data_dir=self.source,auto_import_legacy=False)
        self.dm.registrar_posicao_externa(
            moeda="BTC", quantidade="1", custodia="CUSTODIA_CONFIRMADA",
            data_posicao="2026-01-01", confirmacao_independente=True,
        )
        self.csv=self.root/"historico.csv"
        with self.csv.open("w",encoding="utf-8-sig",newline="") as fp:
            out=csv.DictWriter(fp,fieldnames=COLUNAS)
            out.writeheader()
            out.writerows([_evento(0,"0.5"),_evento(1,"0.1")])
        self.digest=sha256(self.csv.read_bytes()).hexdigest()

    def _ativar(self):
        return ativar_historico_documental(
            self.csv,self.source,sha_confirmado=self.digest)

    def _pacote(self):
        archive=self.root/"portable.zip"
        exportar_pacote(self.dm.arquivo_db,archive)
        return archive

    @staticmethod
    def _reescrever_zip(original,novo,modifier):
        with zipfile.ZipFile(original) as inp:
            files={name:inp.read(name) for name in inp.namelist()}
        modifier(files)
        with zipfile.ZipFile(novo,"w",compression=zipfile.ZIP_DEFLATED) as out:
            for name,content in files.items():
                out.writestr(name,content)

    def test_recovery_restores_active_documentary_csv_manifest_and_rebuilds_sqlite(self):
        original=self._ativar()
        snapshot=self.dm.carregar_posicoes_externas()
        bundle=self._pacote()
        with zipfile.ZipFile(bundle) as archive:
            names=set(archive.namelist())
            self.assertIn("evidencias/historico-ativo.json",names)
            self.assertIn(f"evidencias/historico-{self.digest}.csv",names)
            self.assertIn(f"evidencias/historico-{self.digest}.json",names)
            self.assertNotIn(f"evidencias/livro-{self.digest}.sqlite3",names)
        target=self.root/"recuperado"
        result=recuperar_pacote(bundle,target)
        self.assertFalse(result["ativado"])
        ativo=carregar_historico_ativo(target)
        self.assertEqual(ativo.read_bytes(),self.csv.read_bytes())
        self.assertTrue((target/"evidencias"/f"livro-{self.digest}.sqlite3").is_file())
        with closing(sqlite3.connect(target/"evidencias"/f"livro-{self.digest}.sqlite3")) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0],2)
        restored=DataManager(data_dir=target,auto_import_legacy=False)
        self.assertEqual(restored.carregar_posicoes_externas(),snapshot)
        self.assertEqual(carregar_historico_ativo(self.source).read_bytes(),
                         self.csv.read_bytes())
        self.assertTrue(Path(original["livro"]).is_file())

    def test_modified_evidence_even_with_rewritten_zip_manifest_fails_closed(self):
        self._ativar()
        bundle=self._pacote()
        altered=self.root/"altered.zip"
        name=f"evidencias/historico-{self.digest}.csv"
        def tamper(files):
            files[name]=files[name].replace(b"0.5",b"0.7")
            manifest=json.loads(files["manifest.json"])
            manifest["arquivos"][name]=sha256(files[name]).hexdigest()
            files["manifest.json"]=json.dumps(manifest).encode()
        self._reescrever_zip(bundle,altered,tamper)
        target=self.root/"nao_criar"
        with self.assertRaises((RuntimeError,ValueError)):
            recuperar_pacote(altered,target)
        self.assertFalse(target.exists())

    def test_missing_historical_manifest_fails_before_target_creation(self):
        self._ativar()
        bundle=self._pacote()
        incomplete=self.root/"incomplete.zip"
        name=f"evidencias/historico-{self.digest}.json"
        def omit(files):
            del files[name]
            manifest=json.loads(files["manifest.json"])
            del manifest["arquivos"][name]
            files["manifest.json"]=json.dumps(manifest).encode()
        self._reescrever_zip(bundle,incomplete,omit)
        target=self.root/"nao_criar"
        with self.assertRaisesRegex(RuntimeError,"incompleto"):
            recuperar_pacote(incomplete,target)
        self.assertFalse(target.exists())

    def test_old_wallet_only_bundle_still_recovers(self):
        bundle=self._pacote()
        target=self.root/"legacy-recovery"
        recuperar_pacote(bundle,target)
        self.assertIsNone(carregar_historico_ativo(target))
        self.assertTrue((target/"portfolio.sqlite3").is_file())

    def test_corrupt_active_history_blocks_export_without_overwriting_wallet(self):
        result=self._ativar()
        db=self.dm.arquivo_db
        with closing(sqlite3.connect(db)) as conn:
            before=conn.execute("SELECT COUNT(*) FROM posicoes_externas").fetchone()[0]
        Path(result["arquivo_ativo"]).write_bytes(b"CORROMPIDO")
        bundle=self.root/"nao_gerar.zip"
        with self.assertRaises((ValueError,RuntimeError)):
            exportar_pacote(db,bundle)
        self.assertFalse(bundle.exists())
        with closing(sqlite3.connect(db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM posicoes_externas").fetchone()[0],before)


if __name__=="__main__":
    unittest.main()
