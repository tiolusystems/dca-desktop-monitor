"""Cotação histórica por ativos realmente negociáveis, sem preços sintéticos.

Um airdrop/dust token sem mercado USDT NÃO pode bloquear a consulta de
BTC/ETH/USDT/BRL. Sem ticker comprovado, valor desse ativo fica indisponível.
"""
from __future__ import annotations


def consultar_cotacoes_historicas(price_manager, ativos):
    """Retorna (preços válidos, USDT/BRL válido, ativos sem mercado).

    A consulta de mercados da corretora não presume paridade USDC nem usa
    último preço em cache fora da validade do PriceManager.
    """
    candidatos = sorted({
        str(ativo).upper().strip() for ativo in ativos
        if str(ativo).strip() and str(ativo).upper().strip() not in ("USDT", "BRL")
    })
    exchange = getattr(price_manager, "exchange", None)
    if exchange is None:
        return price_manager.precos_para_avaliacao(), None, candidatos
    try:
        mercados = exchange.load_markets()
        if not isinstance(mercados, dict):
            raise ValueError("Catálogo de mercados inválido")
    except Exception:
        # Nenhum mercado foi verificado; não tentar preços de ativos desconhecidos.
        return price_manager.precos_para_avaliacao(), None, candidatos
    negociaveis = [
        ativo for ativo in candidatos
        if f"{ativo}/USDT" in mercados
        and mercados[f"{ativo}/USDT"].get("active") is not False
    ]
    sem_mercado = sorted(set(candidatos) - set(negociaveis))
    # Atualiza USDT/BRL mesmo se não houver ativos negociáveis.
    price_manager.atualizar_precos(negociaveis)
    return (
        price_manager.precos_para_avaliacao(),
        price_manager.taxa_brl_para_avaliacao(),
        sem_mercado,
    )
