"""Tests for conservative, read-only documentary portfolio valuation."""
from pathlib import Path
from collections import defaultdict
import csv
import tempfile
from unittest import TestCase
from unittest.mock import patch

from backend.historical_live_monitor import calcular_painel_documental


def resumo(*saldos):
    return {"sha256": "a" * 64, "eventos_documentais": 13218,
            "saldos": list(saldos)}


def saldo(ativo, qtd, custodia="BINANCE:Spot", status="SALDO_DERIVADO_NAO_CERTIFICADO"):
    return {"ativo": ativo, "saldo_algebrico": str(qtd),
            "custodia": custodia, "status": status}


class PainelDocumentalTest(TestCase):
    def calculate(self, result, quotes=None, fx=None):
        with patch("backend.historical_live_monitor.reconciliar_historico_documental",
                   return_value=result), patch(
                       "backend.historical_live_monitor._fluxos_brl_documentados",
                       return_value=defaultdict(lambda: {
                           "binance_compra": 0, "binance_venda": 0,
                           "mp_compra_transcrita": 0, "mp_venda_transcrita": 0
                       })):
            return calcular_painel_documental(
                Path("NAO_ABRIR_ORIGEM"), cotacoes_usdt=quotes,
                cambio_usdt_brl=fx, instante_cotacoes="2026-10-24T12:00:00+00:00")

    def test_no_usdc_parity_and_no_invented_cost(self):
        r = self.calculate(resumo(
            saldo("BTC", "0.25"), saldo("BTC", "-0.01", "BINANCE:EARN",
                                      "ORIGEM_INCOMPLETA_SALDO_NEGATIVO"),
            saldo("USDC", "12"), saldo("BRL", "100"), saldo("USDT", "15"),
        ), {"BTC": "90000"}, "5")
        by = {x["ativo"]: x for x in r["ativos"]}
        self.assertEqual(by["USDC"]["estado"], "SEM_COTACAO_ATUAL")
        self.assertEqual(by["USDT"]["valor_brl"], "75")
        self.assertEqual(by["BRL"]["valor_brl"], "100")
        self.assertIsNone(by["BTC"]["valor_brl"])
        self.assertEqual(r["ativos_com_lacuna_custodia"], ["BTC"])
        self.assertIsNone(r["total_documental_nao_certificado_brl"])
        self.assertEqual(r["subtotal_avaliavel_brl"], "175")
        self.assertIsNone(r["custo_brl_consolidado"])
        self.assertIsNone(r["lucro_brl_consolidado"])

    def test_all_quotes_still_block_negative_custody(self):
        r = self.calculate(resumo(
            saldo("BTC", "0.25"), saldo("BTC", "-0.01", "BINANCE:EARN",
                                      "ORIGEM_INCOMPLETA_SALDO_NEGATIVO"),
            saldo("USDC", "12"), saldo("BRL", "100"), saldo("USDT", "15"),
        ), {"BTC": "90000", "USDC": "0.998"}, "5")
        self.assertIsNone(r["total_documental_nao_certificado_brl"])
        self.assertEqual(r["subtotal_avaliavel_usdt"], "46.976")

    def test_fx_absent_never_falls_back_to_ptax(self):
        r = self.calculate(resumo(
            saldo("USDT", "10"), saldo("BRL", "100"),
            saldo("USDC", "20")), {"USDC": "0.999"}, None)
        by = {x["ativo"]: x for x in r["ativos"]}
        self.assertIsNone(r["cambio_atual_usdt_brl"])
        self.assertEqual(by["BRL"]["estado"], "SEM_CAMBIO_ATUAL")
        self.assertIsNone(r["total_documental_nao_certificado_brl"])

    def test_full_quotes_with_no_gap_still_not_certified(self):
        r = self.calculate(resumo(
            saldo("BTC", "0.1"), saldo("USDT", "10")), {"BTC": "95000"}, "5")
        self.assertEqual(r["total_documental_nao_certificado_usdt"], "9510.0")
        self.assertFalse(r["posicao_certificada_pela_corretora"])
        self.assertFalse(r["financeiro_operacional_alterado"])

    def test_historical_negative_even_if_final_positive_is_blocked(self):
        r = self.calculate(resumo(
            saldo("ETH", "1.2", status="HISTORICO_COM_LACUNA_TEMPORAL"),
        ), {"ETH": "4000"}, "5")
        self.assertIsNone(r["ativos"][0]["valor_brl"])
        self.assertEqual(r["ativos"][0]["estado"], "LACUNA_DE_CUSTODIA")

    def test_cotacoes_invalidas_sao_indisponiveis(self):
        r = self.calculate(resumo(saldo("DOGE", "100")),
                           {"DOGE": float("nan")}, -1)
        self.assertIsNone(r["ativos"][0]["valor_usdt"])
        self.assertIsNone(r["cambio_atual_usdt_brl"])

    def test_zero_quantity_never_requires_fake_price(self):
        r = self.calculate(resumo(saldo("NEAR", "0")), {}, None)
        self.assertEqual(r["ativos"][0]["valor_usdt"], "0")
        self.assertEqual(r["ativos"][0]["estado"], "SEM_POSICAO_DOCUMENTAL")
        self.assertEqual(r["lucro_brl_consolidado"], None)

    def test_apuracao_brl_nao_conta_transferencia_como_venda(self):
        from backend.historical_live_monitor import _fluxos_brl_documentados
        from backend.historical_evidence import COLUNAS
        with tempfile.TemporaryDirectory() as root:
            origem=Path(root)/"movimentos.csv"
            def row(**kwargs):
                base={key:"" for key in COLUNAS}
                base.update(kwargs)
                return base
            linhas=[
                row(fonte="BINANCE_SPOT", ativo="BTC", moeda_cotacao="BRL",
                    lado="BUY",valor_cotacao_executado="1200"),
                row(fonte="BINANCE_SPOT", ativo="BTC", moeda_cotacao="BRL",
                    lado="SELL",valor_cotacao_executado="800"),
                row(fonte="MERCADO_PAGO_TRANSCRITO",ativo="BTC",
                    classe_evidencia="COMPRA_BTC_BRL_TRANSCRITA",
                    valor_brl_documentado="1900"),
                row(fonte="MERCADO_PAGO_TRANSCRITO",ativo="BTC",
                    classe_evidencia="TRANSFERENCIA_BTC_EXTERNA_TRANSCRITA",
                    valor_brl_documentado="2200"),
            ]
            with origem.open("w",encoding="utf-8-sig",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=COLUNAS)
                writer.writeheader()
                writer.writerows(linhas)
            result=_fluxos_brl_documentados(origem)
            self.assertEqual(result["BTC"]["binance_compra"],1200)
            self.assertEqual(result["BTC"]["binance_venda"],800)
            self.assertEqual(result["BTC"]["mp_compra_transcrita"],1900)
            self.assertEqual(result["BTC"]["mp_venda_transcrita"],0)
