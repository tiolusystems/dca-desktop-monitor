import unittest
from backend.custody_movements import planejar_movimento, ErroMovimentoCustodia

class CustodyPlanningTests(unittest.TestCase):
    def test_no_fictitious_sale(self):
        p=planejar_movimento(moeda="BTC",origem="Cold wallet",destino="Exchange",
          quantidade="0.2",data="2026-10-18",tipo="transferencia",
          saldo_declarado="0.3")
        self.assertFalse(p.autorizado_para_gravacao)
        self.assertTrue(p.requer_conciliacao)
        self.assertFalse(p.custo_conhecido)
    def test_cannot_oversell_or_move_to_same_custody(self):
        for changes in ({"quantidade":"0.4"},{"destino":"Cold wallet"}):
            args=dict(moeda="BTC",origem="Cold wallet",destino="Exchange",
                      quantidade="0.2",data="2026-10-18",tipo="venda",
                      saldo_declarado="0.3")
            args.update(changes)
            with self.assertRaises(ErroMovimentoCustodia):
                planejar_movimento(**args)

if __name__=="__main__":
    unittest.main()
