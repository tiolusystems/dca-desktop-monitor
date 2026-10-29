"""Contrato da apresentação BRL atual, sem depender do livro histórico em reais."""
import csv
import tempfile
import unittest
from pathlib import Path

from backend.backend import AnalysisEngine
from backend.metricas_exibicao import (
    metricas_ativo,
    metricas_usdt_para_brl_atual,
    totais_exibicao,
    totais_usdt_para_brl_atual,
)
def operacao(moeda, operacao, quantidade, valor, data):
    return {
        "Data": data,
        "Moeda": moeda,
        "Operacao": operacao,
        "Quantidade": quantidade,
        "Preco": float(valor) / float(quantidade),
        "Valor_USDT": valor,
        # A ausência de câmbio histórico não pode bloquear a apresentação atual.
        "Taxa_BRL": 0,
    }


class DashboardBrlPresentationTests(unittest.TestCase):
    """Fixture sintética de 26 operações, sem dados financeiros do usuário."""

    def setUp(self):
        self.rate = 5.25
        with tempfile.TemporaryDirectory() as pasta:
            original = Path(pasta) / "original.csv"
            linhas = [operacao("USDT", "compra", 10000, 10000, "2026-01-01 09:00:00")]
            for indice in range(12):
                dia = indice + 2
                linhas.extend((
                    operacao("BTC", "compra", 1, 100 + indice, f"2026-01-{dia:02d} 10:00:00"),
                    operacao("BTC", "venda", 1, 130 + indice, f"2026-01-{dia:02d} 11:00:00"),
                ))
            linhas.append(operacao("ETH", "compra", 2, 100, "2026-01-20 10:00:00"))
            self.assertEqual(len(linhas), 26)
            with original.open("w", newline="", encoding="utf-8") as arquivo:
                escritor = csv.DictWriter(arquivo, fieldnames=linhas[0].keys())
                escritor.writeheader()
                escritor.writerows(linhas)
            with original.open(encoding="utf-8", newline="") as arquivo:
                self.operacoes = list(csv.DictReader(arquivo))

        self.portfolio = AnalysisEngine.calcular_portfolio(
            self.operacoes, {"BTC": 200, "ETH": 70},
        )
    def _metricas_btc_usdt(self):
        return metricas_ativo(self.portfolio["BTC"], brl=False)

    def _totais_usdt(self):
        dados = {m: d for m, d in self.portfolio.items() if m != "totais"}
        metricas = [metricas_ativo(dados[m], brl=False) for m in dados if m != "USDT (Caixa)"]
        return totais_exibicao(self.portfolio["totais"], metricas, brl=False)

    def test_equivalente_atual_converte_metricas_conhecidas_sem_historico_brl(self):
        base = self._metricas_btc_usdt()
        brl = metricas_usdt_para_brl_atual(base, self.rate)
        self.assertEqual(self.portfolio["BTC"]["quantidade_final"], 0)
        self.assertGreater(base["pl_r"], 0)
        self.assertEqual(brl["pl_r"], base["pl_r"] * self.rate)
        self.assertEqual(brl["pl_tot"], base["pl_tot"] * self.rate)
        self.assertEqual(brl["pmc"], base["pmc"] * self.rate)

    def test_taxa_historica_zero_nao_bloqueia_equivalente_atual(self):
        self.assertTrue(all(linha["Taxa_BRL"] == "0" for linha in self.operacoes))
        base = self._metricas_btc_usdt()
        self.assertIsNotNone(metricas_usdt_para_brl_atual(base, self.rate)["pl_r"])

    def test_percentuais_usdt_e_brl_sao_iguais(self):
        totais = self._totais_usdt()
        custo, pl_nr, _, _, _ = totais
        custo_brl, pl_nr_brl, _, _, _ = totais_usdt_para_brl_atual(totais, self.rate)
        self.assertAlmostEqual(pl_nr / custo * 100, pl_nr_brl / custo_brl * 100)

    def test_alternancia_nao_muta_metricas_usdt(self):
        base = self._metricas_btc_usdt()
        antes = dict(base)
        for _ in range(3):
            exibida = metricas_usdt_para_brl_atual(base, self.rate)
            restaurada = metricas_ativo(self.portfolio["BTC"], brl=False)
            self.assertEqual(exibida["pl_r"], base["pl_r"] * self.rate)
            self.assertEqual(restaurada, base)
        self.assertEqual(base, antes)

    def test_taxa_atual_invalida_mantem_usdt_e_torna_somente_brl_indisponivel(self):
        base = self._metricas_btc_usdt()
        brl = metricas_usdt_para_brl_atual(base, None)
        self.assertTrue(all(brl[campo] is None for campo in ("pmc", "custo", "pl_nr", "pl_r", "pl_tot", "comprado")))
        self.assertEqual(base, self._metricas_btc_usdt())

    def test_none_financeiro_nao_vira_zero_na_conversao(self):
        brl = metricas_usdt_para_brl_atual(
            {"pmc": 10, "custo": None, "pl_nr": None, "pl_r": 2,
             "pl_tot": None, "comprado": 10, "est": False}, self.rate,
        )
        self.assertIsNone(brl["custo"])
        self.assertIsNone(brl["pl_nr"])
        self.assertIsNone(brl["pl_tot"])
        self.assertEqual(brl["pl_r"], 10.5)

if __name__ == "__main__":
    unittest.main()
