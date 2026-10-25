"""NC-03/04: consistent symbol custody, economically valid executed trades."""
import csv
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from backend.historical_evidence import COLUNAS, ErroHistoricoDocumental, validar_historico_documental
from backend.historical_reconciliation import reconciliar_historico_documental
from backend.historical_live_monitor import calcular_painel_documental


def row(n, **changes):
    base={c:"" for c in COLUNAS}
    base.update({
        "data_hora":f"2026-01-01 10:00:{n:02d}",
        "fonte":"BINANCE_TRANSACOES","arquivo_fonte_sha256":"b"*64,
        "linha_fonte":str(n+2),"classe_evidencia":"MOVIMENTO_EXTERNO",
        "impacto_saldo":"SIM_APENAS_SALDO_CONTA_DOCUMENTADA",
        "conta":"Spot","operacao_origem":"Deposit",
        "ativo":"BTC","quantidade_assinada":"0.5",
        "custo_aquisicao":"NAO_DETERMINADO_POR_ESTE_EVENTO",
    })
    base.update(changes)
    key=f'{base["fonte"]}:{base["arquivo_fonte_sha256"]}:{base["linha_fonte"]}:{base["classe_evidencia"]}:{base["data_hora"]}'
    base["id_evento"]=sha256(key.encode()).hexdigest()[:24]
    return base


def spot(n, **changes):
    fields=dict(
        fonte="BINANCE_SPOT",arquivo_fonte_sha256="c"*64,
        classe_evidencia="EXECUCAO_SPOT",
        impacto_saldo="NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE",
        operacao_origem="Trade Spot",par="BTCBRL",moeda_cotacao="BRL",
        lado="BUY",preco_executado="10",
        quantidade_executada="2",valor_cotacao_executado="20",
        quantidade_assinada="2",id_ordem="1234",
    )
    fields.update(changes)
    return row(n, **fields)


class EconomicSemanticTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.src=Path(t.name)/"doc.csv"

    def write(self, rows):
        with self.src.open("w",newline="",encoding="utf-8-sig") as fp:
            w=csv.DictWriter(fp,fieldnames=COLUNAS)
            w.writeheader()
            w.writerows(rows)

    def test_mixed_case_asset_does_not_overwrite_custody(self):
        self.write([row(1),row(2,ativo="btc",quantidade_assinada="0.1")])
        r=reconciliar_historico_documental(self.src)
        self.assertEqual(len(r["saldos"]),1)
        self.assertEqual(r["saldos"][0]["saldo_algebrico"],"0.6")
        panel=calcular_painel_documental(self.src,cotacoes_usdt={"BTC":"100000"},
                                          cambio_usdt_brl="5")
        self.assertEqual(panel["ativos"][0]["quantidade_documental"],"0.6")
        self.assertEqual(panel["ativos"][0]["custodias"],{"BINANCE:Spot":"0.6"})
        self.assertEqual(panel["ativos"][0]["valor_brl"],"300000.0")

    def test_invalid_negative_executed_amount_rejected(self):
        self.write([spot(1,quantidade_executada="-2",valor_cotacao_executado="999")])
        with self.assertRaisesRegex(ErroHistoricoDocumental,"positivo"):
            validar_historico_documental(self.src)

    def test_wrong_pair_rejected(self):
        self.write([spot(1,par="ETHBRL")])
        with self.assertRaisesRegex(ErroHistoricoDocumental,"incompatíveis"):
            validar_historico_documental(self.src)

    def test_incompatible_trade_not_added_to_brl_totals(self):
        self.write([spot(1,preco_executado="10",quantidade_executada="2",
                         valor_cotacao_executado="999")])
        with self.assertRaisesRegex(ErroHistoricoDocumental,"diverge"):
            reconciliar_historico_documental(self.src)

    def test_realistic_decimal_precision_and_fee_token_kept(self):
        self.write([spot(1,preco_executado="21711.67",
                         quantidade_executada="0.092",
                         valor_cotacao_executado="1997.47364",
                         quantidade_assinada="0.092",
                         ativo="ETH",par="ETHBRL",taxa_quantidade="0.000092",taxa_moeda="ETH")])
        doc=validar_historico_documental(self.src)
        self.assertEqual(doc["quantidade"],1)
        r=reconciliar_historico_documental(self.src)
        self.assertEqual(r["spot_brl_documentado"]["compra"],"1997.47364")
        self.assertFalse(r["saldos"])

    def test_micro_rounding_within_documented_tolerance(self):
        self.write([spot(1,valor_cotacao_executado="20.0000005")])
        self.assertEqual(validar_historico_documental(self.src)["quantidade"],1)


if __name__=="__main__":
    unittest.main()
