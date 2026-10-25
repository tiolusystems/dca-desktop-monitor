"""Historical documentary evidence must never mutate the operational SQLite."""
import csv
import json
import os
from unittest.mock import patch
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

    def test_falha_de_publicacao_nao_deixa_csv_parcial_ou_perde_backup(self):
        _write(self.csv, [_row()])
        dados = self.root / "dados"
        dados.mkdir()
        wallet = dados / "portfolio.sqlite3"
        wallet.write_bytes(b"BACKUP-INTOCAVEL")
        sha = validar_historico_documental(self.csv)["sha256"]
        with patch("backend.historical_evidence.os.link",
                   side_effect=OSError("disco cheio")):
            with self.assertRaisesRegex(OSError, "disco cheio"):
                arquivar_historico_documental(self.csv, dados, sha)
        evidencias = dados / "evidencias"
        self.assertFalse((evidencias / f"historico-{sha}.csv").exists())
        self.assertFalse(list(evidencias.glob(".historico-*")))
        self.assertEqual(wallet.read_bytes(), b"BACKUP-INTOCAVEL")
        result = arquivar_historico_documental(self.csv, dados, sha)
        self.assertEqual(Path(result["copia"]).read_bytes(), self.csv.read_bytes())
        self.assertEqual(wallet.read_bytes(), b"BACKUP-INTOCAVEL")

    def test_falha_apos_csv_completo_recupera_manifesto_sem_regravar(self):
        _write(self.csv, [_row()])
        dados = self.root / "dados"
        dados.mkdir()
        sha = validar_historico_documental(self.csv)["sha256"]
        link_real = os.link
        chamadas = [0]
        def falha_somente_no_manifesto(src, dst):
            chamadas[0] += 1
            if chamadas[0] == 2:
                raise OSError("energia interrompida antes do manifesto")
            return link_real(src, dst)
        with patch("backend.historical_evidence.os.link",
                   side_effect=falha_somente_no_manifesto):
            with self.assertRaisesRegex(OSError, "energia interrompida"):
                arquivar_historico_documental(self.csv, dados, sha)
        destino = dados / "evidencias" / f"historico-{sha}.csv"
        self.assertEqual(destino.read_bytes(), self.csv.read_bytes())
        self.assertFalse((dados / "evidencias" / f"historico-{sha}.json").exists())
        retomado = arquivar_historico_documental(self.csv, dados, sha)
        self.assertTrue(retomado["ja_arquivado"])
        self.assertEqual(destino.read_bytes(), self.csv.read_bytes())
        self.assertTrue((dados / "evidencias" / f"historico-{sha}.json").exists())

    def test_manifesto_json_adulterado_recusado_sem_tocar_wallet(self):
        _write(self.csv, [_row()])
        dados = self.root / "dados"
        dados.mkdir()
        wallet = dados / "portfolio.sqlite3"
        wallet.write_bytes(b"ORIGINAL-NAO-MODIFICAR")
        sha = validar_historico_documental(self.csv)["sha256"]
        arquivar_historico_documental(self.csv, dados, sha)
        meta = dados / "evidencias" / f"historico-{sha}.json"
        original = json.loads(meta.read_text(encoding="utf-8"))
        original["quantidade"] = 999
        meta.write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaisesRegex(ErroHistoricoDocumental, "não corresponde"):
            arquivar_historico_documental(self.csv, dados, sha)
        self.assertEqual(wallet.read_bytes(), b"ORIGINAL-NAO-MODIFICAR")
        self.assertEqual(
            (dados / "evidencias" / f"historico-{sha}.csv").read_bytes(),
            self.csv.read_bytes(),
        )

    def test_manifesto_json_corrompido_recusado_sem_regravar_evidencia(self):
        _write(self.csv, [_row()])
        dados = self.root / "dados"
        dados.mkdir()
        sha = validar_historico_documental(self.csv)["sha256"]
        arquivar_historico_documental(self.csv, dados, sha)
        meta = dados / "evidencias" / f"historico-{sha}.json"
        meta.write_text("{json incompleto", encoding="utf-8")
        with self.assertRaisesRegex(ErroHistoricoDocumental, "inválido"):
            arquivar_historico_documental(self.csv, dados, sha)
        self.assertEqual(
            (dados / "evidencias" / f"historico-{sha}.csv").read_bytes(),
            self.csv.read_bytes(),
        )

    def test_mesmo_csv_de_outra_pasta_reaproveita_manifesto_original(self):
        _write(self.csv, [_row()])
        dados = self.root / "dados"
        dados.mkdir()
        sha = validar_historico_documental(self.csv)["sha256"]
        first = arquivar_historico_documental(self.csv, dados, sha)
        outro = self.root / "outra-pasta"
        outro.mkdir()
        caminho2 = outro / "copiado.csv"
        caminho2.write_bytes(self.csv.read_bytes())
        second = arquivar_historico_documental(caminho2, dados, sha)
        self.assertTrue(second["ja_arquivado"])
        self.assertEqual(first["copia"], second["copia"])
        self.assertEqual(Path(second["copia"]).read_bytes(), caminho2.read_bytes())

    def test_manifesto_symlink_recusado_sem_seguir_destino(self):
        _write(self.csv, [_row()])
        dados = self.root / "dados"
        dados.mkdir()
        sha = validar_historico_documental(self.csv)["sha256"]
        evidencias = dados / "evidencias"
        evidencias.mkdir()
        wallet = dados / "portfolio.sqlite3"
        wallet.write_bytes(b"NAO-ESCREVER-AQUI")
        meta = evidencias / f"historico-{sha}.json"
        try:
            meta.symlink_to(wallet)
        except (OSError, NotImplementedError):
            self.skipTest("symlink indisponível no sistema")
        with self.assertRaisesRegex(ErroHistoricoDocumental, "link simbólico"):
            arquivar_historico_documental(self.csv, dados, sha)
        self.assertEqual(wallet.read_bytes(), b"NAO-ESCREVER-AQUI")
        self.assertFalse((evidencias / f"historico-{sha}.csv").exists())

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


    def test_spot_source_cannot_disguise_a_br_lot_as_another_class(self):
        _write(self.csv, [_row(
            classe_evidencia="MOVIMENTO_EXTERNO",
            impacto_saldo="NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE",
            moeda_cotacao="BRL", valor_cotacao_executado="1000",
        )])
        with self.assertRaisesRegex(ErroHistoricoDocumental, "fonte Spot incompatível"):
            validar_historico_documental(self.csv)

    def test_spot_source_rejects_invalid_side_even_when_amount_present(self):
        _write(self.csv, [_row(lado="DEPOSIT")])
        with self.assertRaisesRegex(ErroHistoricoDocumental, "lado Spot inválido"):
            validar_historico_documental(self.csv)

    def test_mp_impact_cannot_be_declared_no_effect_then_counted(self):
        _write(self.csv, [_row(
            fonte="MERCADO_PAGO_TRANSCRITO",
            classe_evidencia="COMPRA_BTC_BRL_TRANSCRITA",
            impacto_saldo="NENHUM", quantidade_assinada="0.01",
            valor_brl_documentado="2000",
        )])
        with self.assertRaisesRegex(ErroHistoricoDocumental, "Mercado Pago incompatível"):
            validar_historico_documental(self.csv)

    def test_mp_outbound_transfer_must_not_increase_custody(self):
        _write(self.csv, [_row(
            fonte="MERCADO_PAGO_TRANSCRITO",
            classe_evidencia="TRANSFERENCIA_BTC_EXTERNA_TRANSCRITA",
            impacto_saldo="SOMENTE_CUSTODIA_MERCADO_PAGO_NAO_ADICIONAR_A_BINANCE",
            operacao_origem="transferência enviada", quantidade_assinada="0.02",
        )])
        with self.assertRaisesRegex(ErroHistoricoDocumental, "deve reduzir a custódia"):
            validar_historico_documental(self.csv)

    def test_mp_buy_and_sell_signs_cannot_be_reversed(self):
        for classe, quantidade, mensagem in [
            ("COMPRA_BTC_BRL_TRANSCRITA", "-0.1", "compra MP"),
            ("VENDA_BTC_BRL_TRANSCRITA", "0.1", "venda MP"),
        ]:
            with self.subTest(classe=classe):
                _write(self.csv, [_row(
                    fonte="MERCADO_PAGO_TRANSCRITO",
                    classe_evidencia=classe,
                    impacto_saldo="SOMENTE_CUSTODIA_MERCADO_PAGO_NAO_ADICIONAR_A_BINANCE",
                    quantidade_assinada=quantidade, valor_brl_documentado="1000",
                )])
                with self.assertRaisesRegex(ErroHistoricoDocumental, mensagem):
                    validar_historico_documental(self.csv)

    def test_legacy_cannot_claim_binance_balance_impact(self):
        _write(self.csv, [_row(
            fonte="DIARIO_LEGADO", classe_evidencia="REGISTRO_LEGADO",
            impacto_saldo="SIM_APENAS_SALDO_CONTA_DOCUMENTADA",
        )])
        with self.assertRaisesRegex(ErroHistoricoDocumental, "sem autorização"):
            validar_historico_documental(self.csv)

    def test_executed_fx_cannot_be_missing_zero_or_negative(self):
        for rate in ("", "0", "-5"):
            with self.subTest(rate=rate):
                _write(self.csv, [_row(
                    fonte="CAMBIO_REAL_BINANCE", classe_evidencia="CAMBIO_EXECUTADO",
                    impacto_saldo="NENHUM", taxa_brl_efetiva=rate,
                )])
                with self.assertRaisesRegex(ErroHistoricoDocumental, "câmbio executado"):
                    validar_historico_documental(self.csv)


if __name__ == "__main__":
    unittest.main()
