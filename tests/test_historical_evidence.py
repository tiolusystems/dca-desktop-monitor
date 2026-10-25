"""Historical documentary evidence must never mutate the operational SQLite."""
import csv
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from backend.historical_evidence import (
    COLUNAS, ErroHistoricoDocumental, arquivar_historico_documental,
    validar_historico_documental,
)

FONTE_SHA = "a" * 64


def _row(**changes):
    base = {key: "" for key in COLUNAS}
    base.update({
        "data_hora": "2026-01-31 15:35:21",
        "fonte": "BINANCE_SPOT",
        "arquivo_fonte_sha256": FONTE_SHA,
        "linha_fonte": "2",
        "classe_evidencia": "EXECUCAO_SPOT",
        "impacto_saldo": "NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE",
        "conta": "Spot", "operacao_origem": "Trade Spot",
        "ativo": "BTC", "quantidade_assinada": "0.02553",
        "moeda_cotacao": "USDT", "par": "BTCUSDT", "lado": "BUY",
        "preco_executado": "78324.02", "quantidade_executada": "0.02553",
        "valor_cotacao_executado": "1999.6122306",
        "taxa_quantidade": "0.00002553", "taxa_moeda": "BTC",
        "id_ordem": "order-confirmada",
        "custo_aquisicao": "NAO_DETERMINADO_POR_ESTE_EVENTO",
    })
    base.update(changes)
    src = (f'{base["fonte"]}:{base["arquivo_fonte_sha256"]}:'
           f'{base["linha_fonte"]}:{base["classe_evidencia"]}:{base["data_hora"]}')
    base["id_evento"] = sha256(src.encode()).hexdigest()[:24]
    return base


def _write(path, rows):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUNAS)
        writer.writeheader()
        writer.writerows(rows)


class HistoricoDocumentalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csv = self.root / "documental.csv"

    def test_arquivo_valido_preserva_taxa_paga_em_ativo_e_nao_zera_cambio(self):
        _write(self.csv, [_row()])
        info = validar_historico_documental(self.csv)
        self.assertEqual(info["quantidade"], 1)
        self.assertEqual(info["classes"], {"EXECUCAO_SPOT": 1})
        self.assertFalse(info["escritura_financeira_alterada"])
        with self.csv.open(encoding="utf-8-sig", newline="") as file:
            registro = next(csv.DictReader(file))
        self.assertEqual(registro["taxa_quantidade"], "0.00002553")
        self.assertEqual(registro["taxa_moeda"], "BTC")
        self.assertEqual(registro["taxa_brl_efetiva"], "")
        self.assertEqual(registro["custo_aquisicao"], "NAO_DETERMINADO_POR_ESTE_EVENTO")

    def test_copia_verificada_arquiva_sem_tocar_sqlite_existente(self):
        _write(self.csv, [_row()])
        pasta = self.root / "dados"
        pasta.mkdir()
        banco = pasta / "portfolio.sqlite3"
        banco.write_bytes(b"CARTEIRA-NAO-TOCAR")
        before = banco.read_bytes()
        sha = validar_historico_documental(self.csv)["sha256"]
        copia = arquivar_historico_documental(self.csv, pasta, sha)
        self.assertTrue(Path(copia["copia"]).exists())
        self.assertEqual(Path(copia["copia"]).read_bytes(), self.csv.read_bytes())
        self.assertEqual(banco.read_bytes(), before)
        novamente = arquivar_historico_documental(self.csv, pasta, sha)
        self.assertTrue(novamente["ja_arquivado"])
        self.assertEqual(banco.read_bytes(), before)

    def test_modificacao_apos_previa_recusada(self):
        _write(self.csv, [_row()])
        antigo = validar_historico_documental(self.csv)["sha256"]
        _write(self.csv, [_row(observacao="nova observacao")])
        with self.assertRaisesRegex(ErroHistoricoDocumental, "mudou"):
            arquivar_historico_documental(self.csv, self.root, antigo)
        self.assertFalse((self.root / "evidencias").exists())

    def test_duplicata_recusada(self):
        mesma = _row()
        _write(self.csv, [mesma, mesma])
        with self.assertRaisesRegex(ErroHistoricoDocumental, "duplicado"):
            validar_historico_documental(self.csv)

    def test_taxa_nativa_exige_moeda_e_nao_pode_ser_convertida(self):
        _write(self.csv, [_row(taxa_moeda="")])
        with self.assertRaisesRegex(ErroHistoricoDocumental, "taxa sem moeda"):
            validar_historico_documental(self.csv)

    def test_transferencia_mp_nao_vira_venda_nem_saldo_binance(self):
        _write(self.csv, [_row(
            fonte="MERCADO_PAGO_TRANSCRITO", classe_evidencia="TRANSFERENCIA_BTC_EXTERNA_TRANSCRITA",
            impacto_saldo="SOMENTE_CUSTODIA_MERCADO_PAGO_NAO_ADICIONAR_A_BINANCE",
            operacao_origem="transferência enviada", quantidade_assinada="-0.02674512",
        )])
        info = validar_historico_documental(self.csv)
        self.assertEqual(info["impactos"]["SOMENTE_CUSTODIA_MERCADO_PAGO_NAO_ADICIONAR_A_BINANCE"], 1)

    def test_ptax_nunca_preenche_taxa_executada(self):
        _write(self.csv, [_row(
            fonte="PTAX_REFERENCIA", classe_evidencia="REFERENCIA_PTAX_USD_BRL",
            impacto_saldo="NENHUM", taxa_brl_efetiva="5.1",
        )])
        with self.assertRaisesRegex(ErroHistoricoDocumental, "PTAX não é câmbio executado"):
            validar_historico_documental(self.csv)

    def test_arquivo_errado_recusado_sem_importacao_legacy(self):
        self.csv.write_text("Data,Moeda,Operacao\n2026-01-01,BTC,compra\n")
        with self.assertRaisesRegex(ErroHistoricoDocumental, "Cabeçalho"):
            validar_historico_documental(self.csv)

    def test_execucao_spot_com_impacto_repetido_recusada(self):
        _write(self.csv, [_row(impacto_saldo="SIM_APENAS_SALDO_CONTA_DOCUMENTADA")])
        with self.assertRaisesRegex(ErroHistoricoDocumental, "duplicar saldo"):
            validar_historico_documental(self.csv)


if __name__ == "__main__":
    unittest.main()
