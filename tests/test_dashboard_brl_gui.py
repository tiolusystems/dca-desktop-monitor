"""Contrato leve do Dashboard, executado onde CustomTkinter está disponível."""
import unittest
from unittest.mock import patch

try:
    import customtkinter  # noqa: F401
except ModuleNotFoundError:
    GUI_DISPONIVEL = False
else:
    GUI_DISPONIVEL = True
    from gui.janela_distribuicao import JanelaDistribuicao
    from widgets.brl_toggle import BRLToggle


class _Var:
    def __init__(self, valor):
        self.valor = valor

    def get(self):
        return self.valor

    def set(self, valor):
        self.valor = valor


class _PrecoComCacheVencido:
    preco_brl = 5.25

    @staticmethod
    def taxa_brl_para_avaliacao():
        return None


@unittest.skipUnless(GUI_DISPONIVEL, "CustomTkinter é instalado pelo CI de interface")
class DashboardBrlGuiTests(unittest.TestCase):
    def _dashboard(self, moeda, taxa):
        painel = JanelaDistribuicao.__new__(JanelaDistribuicao)
        painel.display_currency = moeda
        painel._taxa_brl_valida = taxa
        return painel

    def test_dashboard_converte_metricas_usdt_sem_consultar_livro_historico(self):
        dados = {
            "pmc_final": 100, "custo_posicao_final": 200,
            "lucro_nao_realizado": 40, "lucro_realizado": 30,
            "lucro_total": 70, "total_comprado_usdt": 500,
        }
        usdt = self._dashboard("USD", 5.25)._metricas("BTC", dados)
        brl = self._dashboard("BRL", 5.25)._metricas("BTC", dados)
        self.assertEqual(brl["custo"], usdt["custo"] * 5.25)
        self.assertEqual(brl["pl_r"], usdt["pl_r"] * 5.25)
        self.assertEqual(brl["pl_nr"] / brl["custo"], usdt["pl_nr"] / usdt["custo"])
        self.assertIn("equivalente à cotação atual", JanelaDistribuicao._TXT_BRL_ATUAL)

    def test_toggle_rejeita_cache_brl_vencido(self):
        toggle = BRLToggle.__new__(BRLToggle)
        toggle.var = _Var(True)
        toggle._price_manager = _PrecoComCacheVencido()
        toggle.display_currency = "USD"
        alteracoes = []
        toggle._on_change = alteracoes.append
        with patch("widgets.brl_toggle.messagebox.showwarning") as aviso:
            toggle._on_toggle()
        aviso.assert_called_once()
        self.assertFalse(toggle.var.get())
        self.assertEqual(toggle.display_currency, "USD")
        self.assertEqual(alteracoes, ["USD"])


if __name__ == "__main__":
    unittest.main()
