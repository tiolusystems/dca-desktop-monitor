"""Painel de posições documentadas, independente do CSV legado operacional.

Apenas Binance Transações e transcrição Mercado Pago alteram quantidades.
Execuções Spot são comprovantes redundantes; Earn é movimentação de custódia.
Cotações atuais podem valorizar saldo documental, jamais substituir custo real.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from backend.historical_reconciliation import reconciliar_historico_documental

ZERO = Decimal("0")


def _positivo(value):
    if value is None:
        return None
    try:
        numero = Decimal(str(value))
        return numero if numero.is_finite() and numero > ZERO else None
    except (InvalidOperation, TypeError, ValueError):
        return None



def _fluxos_brl_documentados(arquivo_csv):
    """Gross BRL of documented executions, NOT tax cost or realised profit.

    Binance Spot BRL executions and Mercado Pago user-transcribed purchases
    are different, explicitly labeled evidence classes. MP transfer reference
    BRL must NEVER be treated as proceeds or a second purchase.
    """
    fluxos = defaultdict(lambda: {"binance_compra": ZERO, "binance_venda": ZERO,
                                  "mp_compra_transcrita": ZERO,
                                  "mp_venda_transcrita": ZERO})
    with Path(arquivo_csv).open(encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp, strict=True):
            ativo = row["ativo"].upper()
            if row["fonte"] == "BINANCE_SPOT" and row["moeda_cotacao"] == "BRL":
                tipo = row["lado"].upper()
                campo = ("binance_compra" if tipo == "BUY" else
                         "binance_venda" if tipo == "SELL" else None)
                if campo is None:
                    raise ValueError("Execução BRL tem lado inválido.")
                bruto = Decimal(row["valor_cotacao_executado"])
            elif row["fonte"] == "MERCADO_PAGO_TRANSCRITO" and row["classe_evidencia"] in (
                    "COMPRA_BTC_BRL_TRANSCRITA", "VENDA_BTC_BRL_TRANSCRITA"):
                campo = ("mp_compra_transcrita" if
                         row["classe_evidencia"] == "COMPRA_BTC_BRL_TRANSCRITA"
                         else "mp_venda_transcrita")
                bruto = Decimal(row["valor_brl_documentado"])
            else:
                continue
            if not bruto.is_finite() or bruto < ZERO:
                raise ValueError("Comprovante de valor BRL inválido.")
            fluxos[ativo][campo] += bruto
    return fluxos


def calcular_painel_documental(arquivo_csv: Path, *, cotacoes_usdt=None,
                                cambio_usdt_brl=None, instante_cotacoes=None,
                                resultado_conciliado=None):
    """Apura quantidades por ativo, custo desconhecido e valorização parcial.

    Nunca compensa silenciosamente saldos negativos de uma custódia com saldo
    positivo de outra. Mesmo preços válidos não certificam a carteira real.
    USDC não tem paridade presumida com USDT; PTAX não é USDT/BRL executado.
    """
    # A aba já reconcilia o arquivo uma vez para descobrir quais ativos têm
    # posição. Reconciliar os 13.218 eventos novamente em cada refresh é caro.
    # Aceitar a prévia somente se ainda corresponder ao MESMO CSV byte a byte.
    # A conferência antes e depois da leitura dos fluxos fecha a janela de
    # alteração da fonte entre o resumo e os comprovantes BRL.
    fonte = Path(arquivo_csv)
    if resultado_conciliado is None:
        resultado = reconciliar_historico_documental(fonte)
    else:
        resultado = resultado_conciliado
        if (not isinstance(resultado, dict)
                or not isinstance(resultado.get("sha256"), str)
                or sha256(fonte.read_bytes()).hexdigest() != resultado["sha256"]):
            raise ValueError("Reconciliação anterior não corresponde ao CSV atual.")
    quotes = {str(k).upper(): _positivo(v) for k, v in (cotacoes_usdt or {}).items()}
    fx = _positivo(cambio_usdt_brl)
    fluxos_brl = _fluxos_brl_documentados(fonte)
    if (resultado_conciliado is not None
            and sha256(fonte.read_bytes()).hexdigest() != resultado["sha256"]):
        raise ValueError("CSV alterado durante a apuração documental; resultados recusados.")
    agregado = defaultdict(lambda: {"saldo": ZERO, "custodias": {},
                                    "pendencias": [], "negativo_historico": False})
    for row in resultado["saldos"]:
        ativo = row["ativo"].upper()
        conta = row["custodia"]
        qtd = Decimal(row["saldo_algebrico"])
        item = agregado[ativo]
        item["saldo"] += qtd
        item["custodias"][conta] = str(qtd)
        if qtd < ZERO:
            item["pendencias"].append(
                f"{conta}: saldo final negativo {qtd} {ativo}")
        if row["status"] in ("HISTORICO_COM_LACUNA_TEMPORAL",
                             "ORIGEM_INCOMPLETA_SALDO_NEGATIVO"):
            item["negativo_historico"] = True
            if row["status"] == "HISTORICO_COM_LACUNA_TEMPORAL":
                # Mesmo quando o saldo final volta a ser positivo, não
                # ocultar a falta de lastro anterior. Datas e mínimos
                # vêm da própria sequência documental, nunca inferidos.
                data = row.get("data_primeiro_saldo_negativo") or "não informada"
                minimo = row.get("menor_saldo_no_periodo")
                descricao = f"{conta}: lacuna temporal desde {data}"
                if minimo not in (None, ""):
                    descricao += f"; mínimo {minimo} {ativo}"
                item["pendencias"].append(descricao)

    linhas, com_lacuna = [], []
    subtotal_usdt = subtotal_brl = ZERO
    sem_avaliacao = 0
    ativos_avaliados_usdt = 0
    ativos_avaliados_brl = 0
    for ativo, item in sorted(agregado.items()):
        quantidade = item["saldo"]
        pendencia = bool(item["pendencias"]) or item["negativo_historico"] or quantidade < ZERO
        preco = (Decimal("1") if ativo == "USDT"
                 else Decimal("1") / fx if ativo == "BRL" and fx
                 else quotes.get(ativo))
        if quantidade == ZERO and not pendencia:
            usdt, brl, situacao = ZERO, ZERO, "SEM_POSICAO_DOCUMENTAL"
        elif pendencia:
            usdt, brl, situacao = None, None, "LACUNA_DE_CUSTODIA"
            com_lacuna.append(ativo)
        elif ativo == "BRL":
            brl = quantidade
            usdt = quantidade / fx if fx else None
            situacao = "VALOR_DOCUMENTAL" if fx else "SEM_CAMBIO_ATUAL"
        elif preco is None:
            usdt, brl, situacao = None, None, "SEM_COTACAO_ATUAL"
        else:
            usdt = quantidade * preco
            brl = usdt * fx if fx else None
            situacao = "VALOR_DOCUMENTAL" if fx else "SEM_CAMBIO_ATUAL"
        if usdt is not None:
            subtotal_usdt += usdt
            if quantidade > ZERO:
                ativos_avaliados_usdt += 1
        if brl is not None:
            subtotal_brl += brl
            if quantidade > ZERO:
                ativos_avaliados_brl += 1
        if quantidade != ZERO and (brl is None or usdt is None):
            sem_avaliacao += 1
        linhas.append({
            "ativo": ativo, "quantidade_documental": str(quantidade),
            "custodias": dict(sorted(item["custodias"].items())),
            "cotacao_atual_usdt": str(preco) if preco is not None else None,
            "valor_usdt": str(usdt) if usdt is not None else None,
            "valor_brl": str(brl) if brl is not None else None,
            "estado": situacao,
            "pendencias_custodia": item["pendencias"],
            "lacuna_temporal": item["negativo_historico"],
            "custo_historico_brl": None, "lucro_prejuizo_brl": None,
            "compras_brutas_brl_binance": str(fluxos_brl[ativo]["binance_compra"]),
            "vendas_brutas_brl_binance": str(fluxos_brl[ativo]["binance_venda"]),
            "compras_brutas_brl_mp_transcricao": str(fluxos_brl[ativo]["mp_compra_transcrita"]),
            "vendas_brutas_brl_mp_transcricao": str(fluxos_brl[ativo]["mp_venda_transcrita"]),
        })
    completo = not sem_avaliacao and not com_lacuna
    return {
        "fonte_sha256": resultado["sha256"],
        "eventos_documentais": resultado["eventos_documentais"],
        "quantidade_ativos": len(linhas),
        "posicoes_custodia": len(resultado["saldos"]),
        "instante_cotacoes_utc": instante_cotacoes,
        "cambio_atual_usdt_brl": str(fx) if fx else None,
        "ativos": linhas,
        "subtotal_avaliavel_usdt": (str(subtotal_usdt)
                                     if ativos_avaliados_usdt else None),
        "subtotal_avaliavel_brl": (str(subtotal_brl)
                                    if ativos_avaliados_brl else None),
        "ativos_avaliados_usdt": ativos_avaliados_usdt,
        "ativos_avaliados_brl": ativos_avaliados_brl,
        "total_documental_nao_certificado_usdt": str(subtotal_usdt) if completo else None,
        "total_documental_nao_certificado_brl": str(subtotal_brl) if completo else None,
        "ativos_sem_valor_integral": sem_avaliacao,
        "ativos_com_lacuna_custodia": com_lacuna,
        "posicao_certificada_pela_corretora": False,
        "brutos_brl_nao_sao_custo_fiscal": True,
        "custo_brl_consolidado": None, "lucro_brl_consolidado": None,
        "situacao": ("CONFERENCIA_PENDENTE" if not completo
                    else "DOCUMENTAL_COMPLETO_EM_COTACOES_NAO_CERTIFICADO"),
        "financeiro_operacional_alterado": False,
        "alerta": ("Valores parciais NÃO constituem patrimônio total. "
                   "Nenhum preço, custo ou taxa histórica foi inventado."),
    }
