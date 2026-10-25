"""Painel de posições documentadas, independente do CSV legado operacional.

Apenas Binance Transações e transcrição Mercado Pago alteram quantidades.
Execuções Spot são comprovantes redundantes; Earn é movimentação de custódia.
Cotações atuais podem valorizar saldo documental, jamais substituir custo real.
"""
from __future__ import annotations

from collections import defaultdict
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


def calcular_painel_documental(arquivo_csv: Path, *, cotacoes_usdt=None,
                                cambio_usdt_brl=None, instante_cotacoes=None):
    """Apura quantidades por ativo, custo desconhecido e valorização parcial.

    Nunca compensa silenciosamente saldos negativos de uma custódia com saldo
    positivo de outra. Mesmo preços válidos não certificam a carteira real.
    USDC não tem paridade presumida com USDT; PTAX não é USDT/BRL executado.
    """
    resultado = reconciliar_historico_documental(Path(arquivo_csv))
    quotes = {str(k).upper(): _positivo(v) for k, v in (cotacoes_usdt or {}).items()}
    fx = _positivo(cambio_usdt_brl)
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
            item["pendencias"].append(f"{conta}: saldo negativo")
        if row["status"] in ("HISTORICO_COM_LACUNA_TEMPORAL",
                             "ORIGEM_INCOMPLETA_SALDO_NEGATIVO"):
            item["negativo_historico"] = True

    linhas, com_lacuna = [], []
    subtotal_usdt = subtotal_brl = ZERO
    sem_avaliacao = 0
    ativos_efetivamente_avaliados = 0
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
            if quantidade > ZERO and brl is not None:
                ativos_efetivamente_avaliados += 1
        if brl is not None:
            subtotal_brl += brl
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
                                     if ativos_efetivamente_avaliados else None),
        "subtotal_avaliavel_brl": (str(subtotal_brl)
                                    if ativos_efetivamente_avaliados else None),
        "ativos_efetivamente_avaliados": ativos_efetivamente_avaliados,
        "total_documental_nao_certificado_usdt": str(subtotal_usdt) if completo else None,
        "total_documental_nao_certificado_brl": str(subtotal_brl) if completo else None,
        "ativos_sem_valor_integral": sem_avaliacao,
        "ativos_com_lacuna_custodia": com_lacuna,
        "posicao_certificada_pela_corretora": False,
        "custo_brl_consolidado": None, "lucro_brl_consolidado": None,
        "situacao": ("CONFERENCIA_PENDENTE" if not completo
                    else "DOCUMENTAL_COMPLETO_EM_COTACOES_NAO_CERTIFICADO"),
        "financeiro_operacional_alterado": False,
        "alerta": ("Valores parciais NÃO constituem patrimônio total. "
                   "Nenhum preço, custo ou taxa histórica foi inventado."),
    }
