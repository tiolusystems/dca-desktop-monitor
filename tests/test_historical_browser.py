"""HIST-09: historical transaction browser is read-only and source-pinned."""
import csv
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.historical_activation import ativar_historico_documental, ErroAtivacaoHistorica
from backend.historical_browser import (
    ErroConsultaHistorica, consultar_eventos_historicos,
)
from backend.historical_evidence import COLUNAS


def evento(n, data, ativo, quantidade, *, spot=False):
    linha = {campo: "" for campo in COLUNAS}
    linha.update({
        "data_hora": data,
        "fonte": "BINANCE_SPOT" if spot else "BINANCE_TRANSACOES",
        "arquivo_fonte_sha256": ("d" if spot else "c") * 64,
        "linha_fonte": str(n + 2),
        "classe_evidencia": "EXECUCAO_SPOT" if spot else "MOVIMENTO_EXTERNO",
        "impacto_saldo": ("NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE" if spot
                          else "SIM_APENAS_SALDO_CONTA_DOCUMENTADA"),
        "conta": "Spot", "operacao_origem": "Trade" if spot else "Deposit",
        "ativo": ativo, "quantidade_assinada": "" if spot else quantidade,
        "custo_aquisicao": "NAO_DETERMINADO_POR_ESTE_EVENTO",
    })
    if spot:
        linha.update({
            "id_ordem": "123", "par": "BTCBRL", "lado": "BUY",
            "quantidade_executada": "0.3", "valor_cotacao_executado": "30000",
            "moeda_cotacao": "BRL", "preco_executado": "100000",
        })
    identidade = (
        f'{linha["fonte"]}:{linha["arquivo_fonte_sha256"]}:'
        f'{linha["linha_fonte"]}:{linha["classe_evidencia"]}:{linha["data_hora"]}'
    )
    linha["id_evento"] = sha256(identidade.encode()).hexdigest()[:24]
    return linha


class BrowserHistoricalEventsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.dados = self.folder / "dados"
        self.dados.mkdir()
        self.wallet = self.dados / "portfolio.sqlite3"
        self.wallet.write_bytes(b"CARTEIRA-ORIGINAL-NAO-TOCAR")
        self.csv = self.folder / "historico.csv"
        self.rows = [
            evento(0, "2021-01-01 12:00:00", "BTC", "0.1"),
            evento(1, "2023-02-03 12:00:00", "ETH", "2"),
            evento(2, "2025-02-04 15:00:00", "BTC", "0.3"),
            evento(3, "2025-02-04 15:00:00", "BTC", "", spot=True),
        ]
        with self.csv.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=COLUNAS)
            writer.writeheader()
            writer.writerows(self.rows)
        self.activation = ativar_historico_documental(
            self.csv, self.dados,
            sha_confirmado=sha256(self.csv.read_bytes()).hexdigest(),
        )

    def test_pagination_source_provenance_and_immutable_wallet(self):
        original = self.wallet.read_bytes()
        first = consultar_eventos_historicos(
            self.dados, pagina=1, por_pagina=2,
        )
        second = consultar_eventos_historicos(
            self.dados, pagina=2, por_pagina=2,
        )
        self.assertEqual((first["total"], first["paginas"]), (4, 2))
        self.assertEqual(len(first["eventos"]), 2)
        self.assertEqual(len(second["eventos"]), 2)
        ids = [e["id_evento"] for e in first["eventos"] + second["eventos"]]
        self.assertEqual(len(set(ids)), 4)
        self.assertEqual(first["sha256"], self.activation["sha256"])
        self.assertTrue(first["somente_leitura"])
        self.assertFalse(first["patrimonio_ou_pl_certificado"])
        self.assertEqual(self.wallet.read_bytes(), original)

    def test_filters_by_asset_source_and_inclusive_dates(self):
        self.assertEqual(consultar_eventos_historicos(
            self.dados, ativo="btc")["total"], 3)
        spot = consultar_eventos_historicos(
            self.dados, fonte="BINANCE_SPOT",
        )
        self.assertEqual(spot["total"], 1)
        self.assertEqual(spot["eventos"][0]["impacto_saldo"],
                         "NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE")
        self.assertEqual(spot["eventos"][0]["valor_cotacao_executado"], "30000")
        self.assertEqual(consultar_eventos_historicos(
            self.dados, inicio="2021-01-01", fim="2023-12-31")["total"], 2)
        self.assertEqual(consultar_eventos_historicos(
            self.dados, inicio="2025-02-04", fim="2025-02-04")["total"], 2)
        self.assertEqual(consultar_eventos_historicos(
            self.dados, ativo="USDC")["total"], 0)
        self.assertEqual(self.wallet.read_bytes(), b"CARTEIRA-ORIGINAL-NAO-TOCAR")

    def test_rejects_bad_filters_before_sql_and_prevents_injection(self):
        for params in (
            {"ativo": "BTC' OR 1=1 --"},
            {"fonte": "BINANCE_TRANSACOES' OR 1=1 --"},
            {"ativo": 123},
            {"fonte": 123},
            {"inicio": "2026-02-30"},
            {"inicio": "2026-01-01", "fim": "2025-12-31"},
            {"pagina": 0},
            {"pagina": 100001},
            {"por_pagina": 201},
            {"por_pagina": True},
        ):
            with self.subTest(params=params):
                with self.assertRaises(ErroConsultaHistorica):
                    consultar_eventos_historicos(self.dados, **params)
        self.assertEqual(self.wallet.read_bytes(), b"CARTEIRA-ORIGINAL-NAO-TOCAR")

    def test_tampered_sqlite_payload_is_not_exposed_as_valid_history(self):
        with closing(sqlite3.connect(self.activation["livro"])) as db:
            db.execute("UPDATE eventos SET quantidade_assinada='100000000'")
            db.commit()
        with self.assertRaises((ErroConsultaHistorica, ErroAtivacaoHistorica)):
            consultar_eventos_historicos(self.dados, ativo="BTC")
        self.assertEqual(self.wallet.read_bytes(), b"CARTEIRA-ORIGINAL-NAO-TOCAR")

    def test_original_source_tampering_is_not_exposed(self):
        Path(self.activation["arquivo_ativo"]).write_bytes(b"adulterado")
        with self.assertRaises((ErroConsultaHistorica, ErroAtivacaoHistorica)):
            consultar_eventos_historicos(self.dados)
        self.assertEqual(self.wallet.read_bytes(), b"CARTEIRA-ORIGINAL-NAO-TOCAR")


if __name__ == "__main__":
    unittest.main()
