"""Financial reconciliation: same-time netting, no duplicated trades or invented cost."""
from pathlib import Path
import tempfile
import unittest

import csv
from hashlib import sha256
from backend.historical_evidence import COLUNAS


def _row(**changes):
    base={key:"" for key in COLUNAS}
    base.update({
        "data_hora":"2026-01-31 15:35:21","fonte":"BINANCE_SPOT",
        "arquivo_fonte_sha256":"a"*64,"linha_fonte":"2",
        "classe_evidencia":"EXECUCAO_SPOT",
        "impacto_saldo":"NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE",
        "conta":"Spot","operacao_origem":"Trade Spot",
        "ativo":"BTC","quantidade_assinada":"0.02553",
        "moeda_cotacao":"USDT","par":"BTCUSDT","lado":"BUY",
        "preco_executado":"78324.02","quantidade_executada":"0.02553",
        "valor_cotacao_executado":"1999.6122306",
        "taxa_quantidade":"0.00002553","taxa_moeda":"BTC",
        "id_ordem":"order-confirmada",
        "custo_aquisicao":"NAO_DETERMINADO_POR_ESTE_EVENTO",
    })
    base.update(changes)
    sig=(f'{base["fonte"]}:{base["arquivo_fonte_sha256"]}:'
         f'{base["linha_fonte"]}:{base["classe_evidencia"]}:{base["data_hora"]}')
    base["id_evento"]=sha256(sig.encode()).hexdigest()[:24]
    return base


def _write(path,rows):
    with Path(path).open("w",encoding="utf-8-sig",newline="") as fp:
        writer=csv.DictWriter(fp,fieldnames=COLUNAS)
        writer.writeheader()
        writer.writerows(rows)
from backend.historical_reconciliation import (
    ErroConciliacaoHistorica, reconciliar_historico_documental,
    exportar_saldos_documentais,
)


def tx(linha, data, operation, moeda, amount, *, conta="Spot", classe="OPERACAO_OU_CONVERSAO"):
    return _row(
        fonte="BINANCE_TRANSACOES", classe_evidencia=classe,
        impacto_saldo="SIM_APENAS_SALDO_CONTA_DOCUMENTADA",
        linha_fonte=str(linha), data_hora=data, conta=conta,
        ativo=moeda, quantidade_assinada=str(amount),
        operacao_origem=operation,
        par="", lado="", taxa_quantidade="", taxa_moeda="",
        id_ordem="", quantidade_executada="", valor_cotacao_executado="",
        valor_brl_documentado="", preco_executado="",
    )


class ReconciliaHistoricoTest(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.csv=Path(self.root.name)/"origem.csv"

    def apply(self, rows):
        _write(self.csv,rows)
        return reconciliar_historico_documental(self.csv)

    @staticmethod
    def pos(res, conta, moeda):
        return next(item for item in res["saldos"]
                    if item["custodia"]==conta and item["ativo"]==moeda)

    def test_spot_e_operacoes_de_transacoes_contam_uma_vez(self):
        result=self.apply([
            tx(2,"2026-01-01 10:00:00","Deposit","USDT","100"),
            tx(3,"2026-01-01 10:01:00","Transaction Spend","USDT","-90"),
            tx(4,"2026-01-01 10:01:00","Transaction Buy","BTC","0.001"),
            tx(5,"2026-01-01 10:01:00","Transaction Fee","BTC","-0.000001",
               classe="CORRETAGEM_EM_ATIVO"),
            _row(linha_fonte="2", data_hora="2026-01-01 10:01:00",
                 quantidade_assinada="0.001", quantidade_executada="0.001",
                 taxa_quantidade="0.000001"),
        ])
        btc=self.pos(result,"BINANCE:Spot","BTC")
        self.assertEqual(btc["saldo_algebrico"],"0.000999")
        self.assertEqual(btc["taxas_no_ativo"],"0.000001")
        self.assertEqual(btc["base_de_custo_brl"],"")
        self.assertEqual(self.pos(result,"BINANCE:Spot","USDT")["saldo_algebrico"],"10")
        self.assertEqual(result["status"],"PENDENTE_CONCILIACAO")
        self.assertFalse(result["escritura_financeira_alterada"])

    def test_earn_e_staking_nao_viram_vendas(self):
        r=self.apply([
            tx(2,"2026-02-01 10:00:00","Deposit","BTC","5",classe="MOVIMENTO_EXTERNO"),
            tx(3,"2026-02-01 10:01:00","Simple Earn Flexible Subscription","BTC","-4",
               classe="MOVIMENTO_INTERNO_EARN"),
            tx(4,"2026-02-02 10:01:00","Simple Earn Flexible Redemption","BTC","3",
               classe="MOVIMENTO_INTERNO_EARN"),
            tx(5,"2026-02-02 11:00:00","Simple Earn Flexible Interest","BTC","0.00001",
               classe="RENDIMENTO_EM_ATIVO"),
        ])
        self.assertEqual(self.pos(r,"BINANCE:Spot","BTC")["saldo_algebrico"],"4.00001")
        self.assertEqual(self.pos(r,"BINANCE:EARN","BTC")["saldo_algebrico"],"1")
        self.assertEqual(self.pos(r,"BINANCE:Spot","BTC")["rendimentos_no_ativo"],"0.00001")

    def test_deposito_de_outra_corretora_nao_gera_compra_binance(self):
        r=self.apply([
            tx(2,"2025-05-01 10:01:00","Deposit","BTC","0.04",classe="MOVIMENTO_EXTERNO"),
            _row(
                fonte="MERCADO_PAGO_TRANSCRITO",
                classe_evidencia="TRANSFERENCIA_BTC_EXTERNA_TRANSCRITA",
                impacto_saldo="SOMENTE_CUSTODIA_MERCADO_PAGO_NAO_ADICIONAR_A_BINANCE",
                data_hora="2025-05-01 10:00:00",linha_fonte="2",
                conta="Mercado Pago",ativo="BTC",quantidade_assinada="-0.0401",
                operacao_origem="transferência enviada",taxa_quantidade="",
                taxa_moeda="",id_ordem="",par="",lado="",
                valor_cotacao_executado="",quantidade_executada="",preco_executado="",
            ),
        ])
        self.assertEqual(self.pos(r,"BINANCE:Spot","BTC")["saldo_algebrico"],"0.04")
        mp=self.pos(r,"MERCADO_PAGO:TRANSCRITO","BTC")
        self.assertEqual(mp["saldo_algebrico"],"-0.0401")
        self.assertEqual(mp["status"],"ORIGEM_INCOMPLETA_SALDO_NEGATIVO")
        self.assertEqual(r["negativos_finais"],["MERCADO_PAGO:TRANSCRITO:BTC"])

    def test_taxa_na_mesma_data_hora_nao_produz_falso_negativo(self):
        r=self.apply([
            tx(2,"2025-01-01 12:00:00","Transaction Fee","BTC","-0.00001",
               classe="CORRETAGEM_EM_ATIVO"),
            tx(3,"2025-01-01 12:00:00","Transaction Buy","BTC","0.1"),
        ])
        self.assertEqual(r["negativos_em_alguma_data"],[])
        self.assertEqual(self.pos(r,"BINANCE:Spot","BTC")["saldo_algebrico"],"0.09999")

    def test_saldo_negativo_nao_e_consertado_com_entrada_automatica(self):
        r=self.apply([tx(2,"2026-01-01 12:00:00","Withdraw","BTC","-0.01",
                         classe="MOVIMENTO_EXTERNO")])
        self.assertEqual(self.pos(r,"BINANCE:Spot","BTC")["saldo_algebrico"],"-0.01")
        self.assertIn("BINANCE:Spot:BTC",r["negativos_finais"])

    def test_quantidade_ausente_bloqueia(self):
        with self.assertRaisesRegex(ErroConciliacaoHistorica,"Quantidade histórica ausente"):
            self.apply([tx(2,"2026-01-01 12:00:00","Withdraw","BTC","")])

    def test_exportacao_separada_e_idempotencia_por_proibicao_de_sobrescrita(self):
        r=self.apply([tx(2,"2026-01-01 12:00:00","Deposit","USDT","100")])
        destino=Path(self.root.name)/"saldos.csv"
        exportar_saldos_documentais(r,destino)
        self.assertTrue(destino.exists())
        with self.assertRaisesRegex(ErroConciliacaoHistorica,"já existe"):
            exportar_saldos_documentais(r,destino)
        with self.assertRaisesRegex(ErroConciliacaoHistorica,"já existe"):
            exportar_saldos_documentais(r,self.csv)
        self.assertEqual(self.pos(r,"BINANCE:Spot","USDT")["base_de_custo_brl"],"")

    def test_mercado_pago_compra_em_brl_nao_converte_a_usdt(self):
        r=self.apply([_row(
            fonte="MERCADO_PAGO_TRANSCRITO",
            classe_evidencia="COMPRA_BTC_BRL_TRANSCRITA",
            impacto_saldo="SOMENTE_CUSTODIA_MERCADO_PAGO_NAO_ADICIONAR_A_BINANCE",
            data_hora="2024-01-01 10:00:00",conta="Mercado Pago",
            ativo="BTC",operacao_origem="compra",valor_brl_documentado="200",
            quantidade_assinada="0.001",taxa_quantidade="",taxa_moeda="",
            id_ordem="",par="",lado="",valor_cotacao_executado="",
            quantidade_executada="",preco_executado="",
        )])
        self.assertEqual(r["mp_brl_transcrito"]["compras_brl"],"200")
        self.assertEqual(self.pos(r,"MERCADO_PAGO:TRANSCRITO","BTC")["base_de_custo_brl"],"")


if __name__=="__main__":
    unittest.main()
