"""Missing Binance markets must never block quoted historical assets."""
import unittest

from backend.historical_quotes import consultar_cotacoes_historicas


class FakeExchange:
    def __init__(self, markets):
        self.markets = markets
        self.calls = 0

    def load_markets(self):
        self.calls += 1
        return self.markets


class FakePriceManager:
    def __init__(self, markets):
        self.exchange = FakeExchange(markets) if markets is not None else None
        self.requested = []
        self.quotes = {"USDT": 1.0}
        self.fx = None

    def atualizar_precos(self, symbols):
        self.requested.append(list(symbols))
        for asset in symbols:
            self.quotes[asset] = {"BTC": 100000, "ETH": 3000, "USDC": 0.998}[asset]
        self.fx = 5.2
        return True

    def precos_para_avaliacao(self):
        return dict(self.quotes)

    def taxa_brl_para_avaliacao(self):
        return self.fx


class HistoricalQuoteTests(unittest.TestCase):
    def test_unknown_airdrops_do_not_block_known_btc_eth(self):
        pm = FakePriceManager({
            "BTC/USDT": {"active": True},
            "ETH/USDT": {"active": True},
            "USDC/USDT": {"active": True},
            "DUST/USDT": {"active": False},
        })
        quotes, fx, missing = consultar_cotacoes_historicas(
            pm, ["BTC", "DUST", "ETH", "UNKNOWN", "USDC", "BRL", "USDT"],
        )
        self.assertEqual(pm.requested, [["BTC", "ETH", "USDC"]])
        self.assertEqual(quotes["BTC"], 100000)
        self.assertEqual(quotes["USDC"], 0.998)  # Never assume 1:1.
        self.assertEqual(fx, 5.2)
        self.assertEqual(missing, ["DUST", "UNKNOWN"])

    def test_empty_catalog_does_not_invent_quote(self):
        pm = FakePriceManager({})
        quotes, fx, missing = consultar_cotacoes_historicas(pm, ["BTC"])
        self.assertEqual(quotes, {"USDT": 1.0})
        self.assertEqual(pm.requested, [[]])
        self.assertEqual(fx, 5.2)
        self.assertEqual(missing, ["BTC"])

    def test_no_exchange_fails_closed(self):
        pm = FakePriceManager(None)
        quotes, fx, missing = consultar_cotacoes_historicas(pm, ["BTC"])
        self.assertEqual(pm.requested, [])
        self.assertEqual(quotes, {"USDT": 1.0})
        self.assertIsNone(fx)
        self.assertEqual(missing, ["BTC"])

    def test_duplicate_assets_are_requested_once(self):
        pm = FakePriceManager({"BTC/USDT": {"active": True}})
        _, _, missing = consultar_cotacoes_historicas(
            pm, ["btc", "BTC", " btc ", "BRL", "USDT"],
        )
        self.assertEqual(pm.requested, [["BTC"]])
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
