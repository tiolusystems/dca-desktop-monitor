"""Recovery ZIP x historical CSV: safe, read-only, real-order matching."""
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from backend.historical_evidence import COLUNAS, validar_historico_documental
from backend.recovery_crosscheck import (
    ErroCruzamentoHistorico, auditar_backup_e_historico, exportar_comparacao,
)

def evento(**kw):
    row={key:"" for key in COLUNAS}
    row.update({
        "data_hora":"2026-01-01 10:00:00","fonte":"BINANCE_SPOT",
        "arquivo_fonte_sha256":"a"*64,"linha_fonte":"2",
        "classe_evidencia":"EXECUCAO_SPOT",
        "impacto_saldo":"NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE",
        "conta":"Spot","operacao_origem":"Trade Spot",
        "ativo":"BTC","quantidade_assinada":"0.001",
        "moeda_cotacao":"USDT","par":"BTCUSDT","lado":"BUY",
        "preco_executado":"100000","quantidade_executada":"0.001",
        "valor_cotacao_executado":"100",
        "taxa_quantidade":"0.000001","taxa_moeda":"BTC",
        "id_ordem":"ORDER-1","custo_aquisicao":"NAO_DETERMINADO_POR_ESTE_EVENTO",
    })
    row.update(kw)
    identity=(f'{row["fonte"]}:{row["arquivo_fonte_sha256"]}:'
              f'{row["linha_fonte"]}:{row["classe_evidencia"]}:{row["data_hora"]}')
    row["id_evento"]=sha256(identity.encode()).hexdigest()[:24]
    return row

class BackupCrossCheckTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.zip=self.root/"DCA-Recuperacao.zip"
        self.document=self.root/"documento.csv"
        self.db=self.root/"original.sqlite3"
        con=sqlite3.connect(self.db)
        con.execute("CREATE TABLE identidade_carteira(id INTEGER PRIMARY KEY, uuid TEXT)")
        con.execute("INSERT INTO identidade_carteira VALUES(1,'EXAMPLE-UUID')")
        con.execute("CREATE TABLE operacoes (id INTEGER PRIMARY KEY,data TEXT,moeda TEXT,operacao TEXT,valor_usdt TEXT,preco TEXT,quantidade TEXT)")
        con.execute("INSERT INTO operacoes VALUES (1,'2026-01-01 10:00:00','BTC','compra','100','100000','0.001')")
        con.execute("CREATE TABLE posicoes_iniciais(id INTEGER)")
        con.execute("CREATE TABLE posicoes_externas(id INTEGER)")
        con.execute("CREATE TABLE movimentacoes_custodia(id INTEGER)")
        con.execute("PRAGMA user_version=10")
        con.commit()
        con.close()
        original=io.StringIO()
        w=csv.DictWriter(original,fieldnames=[
            "Data","Moeda","Operacao","Valor_USDT","Preco","Quantidade","Taxa_BRL"])
        w.writeheader()
        w.writerow({"Data":"2026-01-01 10:00:00","Moeda":"BTC","Operacao":"compra",
                    "Valor_USDT":"100","Preco":"100000","Quantidade":"0.001","Taxa_BRL":"0"})
        contents={
            "portfolio.sqlite3":self.db.read_bytes(),
            "original.csv":original.getvalue().encode("utf-8"),
            "app-settings.json":b"{}","user-config.json":b"{}",
        }
        meta={"formato":"DCA-RECOVERY-1","schema":10,"uuid":"EXAMPLE-UUID",
              "arquivos":{key:sha256(val).hexdigest() for key,val in contents.items()}}
        with zipfile.ZipFile(self.zip,"w") as z:
            z.writestr("manifest.json",json.dumps(meta))
            for name,val in contents.items():
                z.writestr(name,val)
        self.rows=[
            evento(),
            evento(fonte="DIARIO_LEGADO",arquivo_fonte_sha256="b"*64,
                   linha_fonte="2",classe_evidencia="OPERACAO_LEGADA_PARA_CONCILIAR",
                   impacto_saldo="NAO_SOMAR_ORIGEM_NAO_VERIFICADA",
                   operacao_origem="compra",conta="DCA original",
                   par="",lado="",taxa_quantidade="",taxa_moeda="",id_ordem="",
                   quantidade_executada="",valor_cotacao_executado="100"),
            evento(fonte="BINANCE_TRANSACOES",arquivo_fonte_sha256="c"*64,
                   linha_fonte="2",classe_evidencia="MOVIMENTO_EXTERNO",
                   impacto_saldo="SIM_APENAS_SALDO_CONTA_DOCUMENTADA",
                   operacao_origem="Deposit",quantidade_assinada="0.001",
                   par="",lado="",taxa_quantidade="",taxa_moeda="",id_ordem="",
                   quantidade_executada="",valor_cotacao_executado=""),
        ]
        self.write_doc()

    def write_doc(self):
        with self.document.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=COLUNAS)
            w.writeheader()
            w.writerows(self.rows)

    def test_pacote_original_e_taxa_em_btc_nao_editados(self):
        before_zip=self.zip.read_bytes()
        before_db=self.db.read_bytes()
        before_doc=self.document.read_bytes()
        r=auditar_backup_e_historico(self.zip,self.document)
        self.assertEqual(r["operacoes_sqlite"],1)
        self.assertEqual(r["ordens_spot"],1)
        self.assertEqual(r["correspondencias"],1)
        self.assertEqual(r["ordens_spot_ausentes"],0)
        self.assertEqual(r["comparacoes"][0]["taxas_reais_por_moeda"],"0.000001 BTC")
        self.assertFalse(r["financeiro_alterado"])
        self.assertEqual(self.zip.read_bytes(),before_zip)
        self.assertEqual(self.db.read_bytes(),before_db)
        self.assertEqual(self.document.read_bytes(),before_doc)
        path=self.root/"auditoria.csv"
        self.assertEqual(exportar_comparacao(r,path),str(path))
        with self.assertRaisesRegex(ErroCruzamentoHistorico,"existente"):
            exportar_comparacao(r,path)

    def test_moeda_usdc_separada_da_usdt(self):
        for x in self.rows:
            if x["fonte"]=="BINANCE_SPOT":
                x.update(par="BTCUSDC",moeda_cotacao="USDC")
        self.write_doc()
        r=auditar_backup_e_historico(self.zip,self.document)
        self.assertEqual(r["cotadas_nao_usdt"],1)
        self.assertEqual(r["comparacoes"][0]["status"],"COTADO_OUTRA_MOEDA")

    def test_diario_alheio_e_rejeitado(self):
        for x in self.rows:
            if x["fonte"]=="DIARIO_LEGADO":
                x["quantidade_assinada"]="0.002"
        self.write_doc()
        with self.assertRaisesRegex(ErroCruzamentoHistorico,"não corresponde"):
            auditar_backup_e_historico(self.zip,self.document)

    def test_hash_de_backup_alterado_e_rejeitado(self):
        with zipfile.ZipFile(self.zip) as z:
            records={item.filename:z.read(item.filename) for item in z.infolist()}
        records["original.csv"]=b"alterado"
        with zipfile.ZipFile(self.zip,"w") as z:
            for k,v in records.items():
                z.writestr(k,v)
        with self.assertRaisesRegex(ErroCruzamentoHistorico,"Pacote"):
            auditar_backup_e_historico(self.zip,self.document)

    def extend_backup_with_history(self):
        with zipfile.ZipFile(self.zip) as z:
            files={entry.filename:z.read(entry.filename) for entry in z.infolist()}
        meta=json.loads(files["manifest.json"])
        historico=self.document.read_bytes()
        digest=sha256(historico).hexdigest()
        pointer={
            "schema":1,"sha256":digest,
            "arquivo":f"historico-{digest}.csv",
            "eventos":len(self.rows),
            "status":"HISTORICO_DOCUMENTAL_NAO_CERTIFICADO",
        }
        items={
            "evidencias/historico-ativo.json":json.dumps(pointer).encode(),
            f"evidencias/historico-{digest}.csv":historico,
            f"evidencias/historico-{digest}.json":json.dumps(
                validar_historico_documental(self.document)).encode(),
        }
        files.update(items)
        meta["arquivos"].update({
            name:sha256(data).hexdigest() for name,data in items.items()
        })
        files["manifest.json"]=json.dumps(meta).encode()
        with zipfile.ZipFile(self.zip,"w") as z:
            for k,v in files.items():
                z.writestr(k,v)
        return digest

    def test_crosscheck_accepts_new_recovery_with_active_document_history(self):
        digest=self.extend_backup_with_history()
        result=auditar_backup_e_historico(self.zip,self.document)
        self.assertEqual(result["operacoes_sqlite"],1)
        self.assertEqual(result["correspondencias"],1)
        self.assertFalse(result["financeiro_alterado"])
        with zipfile.ZipFile(self.zip) as z:
            self.assertIn(f"evidencias/historico-{digest}.csv",z.namelist())

    def test_crosscheck_refuses_incomplete_new_history_even_with_updated_hashes(self):
        self.extend_backup_with_history()
        with zipfile.ZipFile(self.zip) as z:
            files={item.filename:z.read(item.filename) for item in z.infolist()}
        extra=next(n for n in files if n.startswith("evidencias/historico-")
                   and n.endswith(".json") and n!="evidencias/historico-ativo.json")
        files.pop(extra)
        metadata=json.loads(files["manifest.json"])
        metadata["arquivos"].pop(extra)
        files["manifest.json"]=json.dumps(metadata).encode()
        with zipfile.ZipFile(self.zip,"w") as z:
            for k,v in files.items():z.writestr(k,v)
        with self.assertRaisesRegex(ErroCruzamentoHistorico,"inválido|incompleto"):
            auditar_backup_e_historico(self.zip,self.document)


    def rewrite_zip(self, files):
        metadata=json.loads(files["manifest.json"])
        metadata["arquivos"]={
            name:sha256(data).hexdigest() for name,data in files.items()
            if name!="manifest.json"
        }
        files["manifest.json"]=json.dumps(metadata).encode()
        with zipfile.ZipFile(self.zip,"w") as z:
            for name,data in files.items():
                z.writestr(name,data)

    def test_crosscheck_rejects_tampered_evidence_manifest_even_if_zip_rehashed(self):
        digest=self.extend_backup_with_history()
        with zipfile.ZipFile(self.zip) as z:
            files={item.filename:z.read(item.filename) for item in z.infolist()}
        name=f"evidencias/historico-{digest}.json"
        manifest=json.loads(files[name])
        manifest["quantidade"]=999
        files[name]=json.dumps(manifest).encode()
        self.rewrite_zip(files)
        with self.assertRaisesRegex(ErroCruzamentoHistorico,"inválido"):
            auditar_backup_e_historico(self.zip,self.document)

    def test_crosscheck_rejects_invalid_pointer_even_if_zip_rehashed(self):
        self.extend_backup_with_history()
        with zipfile.ZipFile(self.zip) as z:
            files={item.filename:z.read(item.filename) for item in z.infolist()}
        name="evidencias/historico-ativo.json"
        pointer=json.loads(files[name])
        pointer["arquivo"]="historico-inexistente.csv"
        files[name]=json.dumps(pointer).encode()
        self.rewrite_zip(files)
        with self.assertRaisesRegex(ErroCruzamentoHistorico,"inválido"):
            auditar_backup_e_historico(self.zip,self.document)

    def test_crosscheck_rejects_non_object_pointer_without_unhandled_error(self):
        self.extend_backup_with_history()
        with zipfile.ZipFile(self.zip) as z:
            files={item.filename:z.read(item.filename) for item in z.infolist()}
        files["evidencias/historico-ativo.json"]=b"[]"
        self.rewrite_zip(files)
        with self.assertRaisesRegex(ErroCruzamentoHistorico,"inválido"):
            auditar_backup_e_historico(self.zip,self.document)


if __name__=="__main__":
    unittest.main()
