from __future__ import annotations

import math


_CAMPOS_MONETARIOS = ("pmc", "custo", "pl_nr", "pl_r", "pl_tot", "comprado")


def _num(valor):
    return None if valor is None else float(valor)


def taxa_brl_atual_valida(taxa_brl) -> float | None:
    """Retorna a taxa atual utilizável apenas para apresentação monetária."""
    try:
        taxa = float(taxa_brl)
    except (TypeError, ValueError):
        return None
    return taxa if math.isfinite(taxa) and taxa > 0 else None


def metricas_usdt_para_brl_atual(metricas: dict, taxa_brl) -> dict:
    """Converte métricas já apuradas em USDT para equivalente BRL atual.

    Esta função não consulta nem substitui o livro histórico em BRL.  ``None``
    continua significando dado financeiro desconhecido; sem uma taxa atual
    válida, toda métrica monetária também permanece indisponível.
    """
    taxa = taxa_brl_atual_valida(taxa_brl)
    resultado = dict(metricas)
    for campo in _CAMPOS_MONETARIOS:
        valor = metricas.get(campo)
        resultado[campo] = None if valor is None or taxa is None else valor * taxa
    return resultado


def totais_usdt_para_brl_atual(totais: tuple, taxa_brl) -> tuple:
    """Converte os totais do Dashboard sem alterar o indicador ``estimado``."""
    custo, pl_nr, pl_r, comprado, estimado = totais
    taxa = taxa_brl_atual_valida(taxa_brl)

    def converter(valor):
        return None if valor is None or taxa is None else valor * taxa

    return converter(custo), converter(pl_nr), converter(pl_r), converter(comprado), estimado


def metricas_ativo(dados: dict, livro_brl: dict | None = None, *,
                   brl: bool = False, taxa_brl: float | None = None) -> dict:
    est = dados.get("estimado", False)
    if not brl:
        return {
            "pmc": dados.get("pmc_final", 0),
            "custo": dados.get("custo_posicao_final", 0),
            "pl_nr": dados.get("lucro_nao_realizado"),
            "pl_r": dados.get("lucro_realizado", 0),
            "pl_tot": dados.get("lucro_total"),
            "comprado": dados.get("total_comprado_usdt", 0),
            "est": est,
        }
    if livro_brl is None:
        return {"pmc": None, "custo": None, "pl_nr": None, "pl_r": None,
                "pl_tot": None, "comprado": 0, "est": est}
    aberta = dados.get("quantidade_final", 0) > 1e-9
    qtd_livro = float(livro_brl["quantidade"])
    custo = _num(livro_brl["custo_aberto"])
    if custo is not None and not aberta:
        custo = 0.0
    pmc = (None if custo is None else
           custo / qtd_livro if aberta and qtd_livro > 1e-12 else 0.0)
    v_atual = dados.get("valor_atual_posicao")
    if custo is None:
        pl_nr = None
    elif not aberta:
        pl_nr = 0.0
    elif v_atual is None or taxa_brl is None:
        pl_nr = None
    else:
        pl_nr = v_atual * taxa_brl - custo
    pl_r = _num(livro_brl["realizado_historico"])
    return {
        "pmc": pmc, "custo": custo, "pl_nr": pl_nr, "pl_r": pl_r,
        "pl_tot": None if pl_nr is None or pl_r is None else pl_nr + pl_r,
        "comprado": _num(livro_brl["compras_historicas"]) or 0,
        "est": est or livro_brl.get("estimado", False),
    }


def totais_exibicao(resumo: dict, metricas: list[dict], totais_brl: dict | None = None,
                    *, brl: bool = False) -> tuple:
    est = resumo.get("estimado", False)
    if not brl:
        return (resumo.get("investido_liquido", 0), resumo.get("nao_realizado"),
                resumo.get("realizado", 0), resumo.get("compras_historicas_usdt", 0), est)

    def soma(chave):
        if any(x[chave] is None for x in metricas):
            return None
        return sum(x[chave] for x in metricas)

    comprado = (totais_brl or {}).get("compras_historicas")
    return (soma("custo"), soma("pl_nr"), soma("pl_r"),
            None if comprado is None else float(comprado),
            est or any(x["est"] for x in metricas))
