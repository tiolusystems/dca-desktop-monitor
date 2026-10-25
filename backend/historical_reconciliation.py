"""Reconciliação financeira de evidências históricas, SEM gravar no SQLite.

O relatório de transações Binance, e não as execuções Spot adicionais, é a
única fonte de variações de saldo Binance. Subscrições/resgates de Earn
transferem custódia; custos desconhecidos não são zerados e não há P/L.
Mercado Pago é livro separado, baseado em transcrição, sem dupla contabilização.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from backend.historical_evidence import validar_historico_documental

ZERO = Decimal("0")
EARN_MOVIMENTOS = {
    "Simple Earn Flexible Subscription": "EARN",
    "Simple Earn Flexible Redemption": "EARN",
    "Staking Purchase": "STAKING",
    "Staking Redemption": "STAKING",
}
CAMPOS_SALDO = (
    "custodia", "ativo", "entradas_documentadas", "saidas_documentadas",
    "saldo_algebrico", "menor_saldo_no_periodo", "data_primeiro_saldo_negativo",
    "taxas_no_ativo", "rendimentos_no_ativo", "status", "base_de_custo_brl",
    "observacao",
)


class ErroConciliacaoHistorica(ValueError):
    pass


def _dec(texto):
    if texto is None or not str(texto).strip():
        raise ErroConciliacaoHistorica("Quantidade histórica ausente; nunca substituir por zero.")
    n = Decimal(str(texto).strip())
    if not n.is_finite():
        raise ErroConciliacaoHistorica("Quantidade histórica não finita.")
    return n


def _novo():
    return {
        "entradas": ZERO, "saidas": ZERO, "saldo": ZERO, "menor": ZERO,
        "primeiro_negativo": "", "taxas": ZERO, "rendimentos": ZERO,
        "eventos": 0,
    }


def _aplicar(estado, delta, dia, classe):
    if delta >= ZERO:
        estado["entradas"] += delta
    else:
        estado["saidas"] -= delta
    estado["saldo"] += delta
    estado["eventos"] += 1
    if estado["saldo"] < estado["menor"]:
        estado["menor"] = estado["saldo"]
        if not estado["primeiro_negativo"]:
            estado["primeiro_negativo"] = dia
    if classe == "CORRETAGEM_EM_ATIVO":
        estado["taxas"] += -delta  # Somente taxas negativas documentadas
    elif classe == "RENDIMENTO_EM_ATIVO":
        estado["rendimentos"] += delta


def reconciliar_historico_documental(origem: Path) -> dict:
    """Obtém posições documentais POR CUSTÓDIA.

    Não representa saldo certificado pela corretora nem considera eventos
    em CSVs de outras fontes como novas compras Binance. Quando negativo,
    marca lacuna de custódia; jamais corrige com depósito artificial.
    """
    meta = validar_historico_documental(origem)
    movimentos = []
    fontes = Counter()
    contagens = Counter()
    pares_brl = {"compra": ZERO, "venda": ZERO}
    pares_brl_execucoes = Counter()
    conversoes_cambio_efetivo = 0
    mp_declarado = {"compras_brl": ZERO, "vendas_brl": ZERO}
    falhas = []
    with Path(origem).open("r", encoding="utf-8-sig", newline="") as fp:
        for linha_csv, row in enumerate(csv.DictReader(fp), 2):
            src, classe = row["fonte"], row["classe_evidencia"]
            fontes[src] += 1
            contagens[classe] += 1
            dia = row["data_hora"]
            ativo = row["ativo"]
            if src == "BINANCE_TRANSACOES":
                if not ativo:
                    raise ErroConciliacaoHistorica(f"Linha {linha_csv}: ativo Binance ausente.")
                delta = _dec(row["quantidade_assinada"])
                conta = row["conta"]
                if not conta:
                    raise ErroConciliacaoHistorica(f"Linha {linha_csv}: conta Binance ausente.")
                movimentos.append((dia, linha_csv, f"BINANCE:{conta}", ativo, delta, classe))
                if row["operacao_origem"] in EARN_MOVIMENTOS:
                    sub = row["operacao_origem"]
                    destino = EARN_MOVIMENTOS[sub]
                    # Saída do Spot para Earn => entrada em custódia Earn, e vice-versa.
                    movimentos.append((dia, linha_csv, f"BINANCE:{destino}", ativo, -delta,
                                       "TRANSFERENCIA_INTERNA_EARN"))
            elif src == "MERCADO_PAGO_TRANSCRITO":
                # Transcrição: representa somente movimentação declarada nessa custódia.
                # Não se deduz taxa da diferença na chegada à Binance.
                delta = _dec(row["quantidade_assinada"])
                movimentos.append((dia, linha_csv, "MERCADO_PAGO:TRANSCRITO", ativo, delta,
                                   classe))
                if classe == "COMPRA_BTC_BRL_TRANSCRITA":
                    mp_declarado["compras_brl"] += _dec(row["valor_brl_documentado"])
                if classe == "VENDA_BTC_BRL_TRANSCRITA":
                    mp_declarado["vendas_brl"] += _dec(row["valor_brl_documentado"])
            elif src == "BINANCE_SPOT":
                # Executado em BRL é documentalmente custo/receita bruta em BRL.
                # Não garante o custo TOTAL da posição (taxas, custódia externa).
                if row["moeda_cotacao"] == "BRL":
                    lado = row["lado"].upper()
                    if lado not in ("BUY", "SELL"):
                        raise ErroConciliacaoHistorica(f"Linha {linha_csv}: lado Spot inválido.")
                    valor = _dec(row["valor_cotacao_executado"])
                    if valor < ZERO:
                        raise ErroConciliacaoHistorica(f"Linha {linha_csv}: valor Spot negativo.")
                    pares_brl["compra" if lado == "BUY" else "venda"] += valor
                    pares_brl_execucoes[lado] += 1
            elif src == "CAMBIO_REAL_BINANCE":
                if not row["taxa_brl_efetiva"]:
                    raise ErroConciliacaoHistorica(
                        f"Linha {linha_csv}: conversão declarada sem câmbio comprovado.")
                conversoes_cambio_efetivo += 1
            # DIARIO_LEGADO, PTAX e SPOT: jamais adicionar ao saldo Binance

    # Agrupamento por horário evita saldo negativo artificial quando taxa,
    # compra e gasto aparecem em várias linhas no mesmo segundo.
    agrupados = defaultdict(lambda: ZERO)
    # HIST-10: o agrupamento por segundo serve SOMENTE para a cronologia.
    # Somar as entradas e saídas depois de compensar compras e vendas do
    # mesmo segundo apagava volume bruto real, embora o saldo líquido
    # permanecesse correto. Guardar fluxos brutos por evento/custódia.
    brutos = defaultdict(lambda: {"entradas": ZERO, "saidas": ZERO})
    for dia, i, conta, ativo, delta, classe in movimentos:
        chave = (dia, conta, ativo)
        agrupados[chave] += delta
        if delta >= ZERO:
            brutos[(conta, ativo)]["entradas"] += delta
        else:
            brutos[(conta, ativo)]["saidas"] -= delta
    estados = defaultdict(_novo)
    for (dia, conta, ativo), delta in sorted(agrupados.items()):
        # Taxas e juros são retidos separadamente em sua quantidade original;
        # o efeito financeiro já está no delta agregado, não se reaplica.
        estado = estados[(conta, ativo)]
        estado["saldo"] += delta
        estado["eventos"] += 1
        if estado["saldo"] < estado["menor"]:
            estado["menor"] = estado["saldo"]
            if not estado["primeiro_negativo"]:
                estado["primeiro_negativo"] = dia

    # Entradas e saídas não são o netting intrassegundo: preservam
    # rigorosamente o fluxo documentado. Em especial, Earn/Spot representam
    # custodias distintas, não vendas nem novos investimentos.
    for chave, valores in brutos.items():
        estados[chave]["entradas"] = valores["entradas"]
        estados[chave]["saidas"] = valores["saidas"]

    for dia, i, conta, ativo, delta, classe in movimentos:
        estado = estados[(conta, ativo)]
        if classe == "CORRETAGEM_EM_ATIVO":
            if delta >= ZERO:
                raise ErroConciliacaoHistorica(f"Linha {i}: corretagem não negativa.")
            estado["taxas"] -= delta
        if classe == "RENDIMENTO_EM_ATIVO":
            if delta < ZERO:
                raise ErroConciliacaoHistorica(f"Linha {i}: rendimento negativo.")
            estado["rendimentos"] += delta

    saldos = []
    negativos_finais = []
    negativos_em_alguma_data = []
    for (conta, ativo), item in sorted(estados.items()):
        deficit = item["menor"] < ZERO
        negativo_final = item["saldo"] < ZERO
        status = ("ORIGEM_INCOMPLETA_SALDO_NEGATIVO" if negativo_final
                  else "HISTORICO_COM_LACUNA_TEMPORAL" if deficit
                  else "SALDO_DERIVADO_NAO_CERTIFICADO")
        nota = ("Não é custódia certificada nem custo fiscal. "
                "Transcrição particular." if conta.startswith("MERCADO_PAGO:")
                else "Saldos por movimentações; requer conferência com Binance. "
                     "Earn inferido por transferências, sem extrato de saldo final.")
        saldos.append({
            "custodia": conta, "ativo": ativo,
            "entradas_documentadas": str(item["entradas"]),
            "saidas_documentadas": str(item["saidas"]),
            "saldo_algebrico": str(item["saldo"]),
            "menor_saldo_no_periodo": str(item["menor"]),
            "data_primeiro_saldo_negativo": item["primeiro_negativo"],
            "taxas_no_ativo": str(item["taxas"]),
            "rendimentos_no_ativo": str(item["rendimentos"]),
            "status": status, "base_de_custo_brl": "",
            "observacao": nota,
        })
        if negativo_final:
            negativos_finais.append(f"{conta}:{ativo}")
        if deficit:
            negativos_em_alguma_data.append(f"{conta}:{ativo}")

    return {
        "arquivo": str(Path(origem)), "sha256": meta["sha256"],
        "eventos_documentais": meta["quantidade"],
        "movimentos_contabilizados": sum(1 for m in movimentos
                                         if m[2].startswith("BINANCE:")),
        "movimentos_mercado_pago": fontes["MERCADO_PAGO_TRANSCRITO"],
        "fontes": dict(fontes), "classes": dict(contagens),
        "saldos": saldos,
        "negativos_finais": negativos_finais,
        "negativos_em_alguma_data": negativos_em_alguma_data,
        "spot_brl_documentado": {k: str(v) for k, v in pares_brl.items()},
        "spot_brl_execucoes": dict(pares_brl_execucoes),
        "mp_brl_transcrito": {k: str(v) for k, v in mp_declarado.items()},
        "conversoes_brl_usdt_comprovadas": conversoes_cambio_efetivo,
        "status": "PENDENTE_CONCILIACAO",
        "escritura_financeira_alterada": False,
        "observacao": (
            "Saldos provisórios por custódia, NÃO ativos do painel DCA. "
            "Não somar Spot e Earn como negociações. Custo de aquisição, "
            "taxas externas e P/L BRL permanecem desconhecidos sem comprovante."
        ),
    }


def exportar_saldos_documentais(resultado: dict, destino: Path) -> Path:
    """CSV isolado de prévia; nunca sobrescreve banco ou histórico original."""
    caminho = Path(destino).expanduser().resolve()
    if caminho.exists():
        raise ErroConciliacaoHistorica("O destino já existe; não sobrescrever relatório anterior.")
    if caminho.suffix.lower() != ".csv":
        raise ErroConciliacaoHistorica("Destino do relatório precisa ser CSV.")
    if Path(resultado["arquivo"]).resolve() == caminho:
        raise ErroConciliacaoHistorica("Nunca substituir CSV documental original.")
    with caminho.open("x", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=CAMPOS_SALDO)
        writer.writeheader()
        writer.writerows(resultado["saldos"])
    return caminho
