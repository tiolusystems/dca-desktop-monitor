"""Custody movement contract: no fabricated trades, funding, or acquisition costs.

The current external-position table stores a DECLARED SNAPSHOT, not an event
ledger. A snapshot cannot be safely reduced for a withdrawal or sale without
an append-only movement ledger and temporal valuation changes. This module
provides an explicit, validated planning boundary for that next operation.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import date

class ErroMovimentoCustodia(ValueError):
    pass

@dataclass(frozen=True)
class PlanoMovimento:
    moeda: str
    origem: str
    destino: str
    quantidade: str
    data: str
    tipo: str
    custo_conhecido: bool
    requer_conciliacao: bool = True
    autorizado_para_gravacao: bool = False


def planejar_movimento(*, moeda: str, origem: str, destino: str,
                       quantidade: str, data: str, tipo: str,
                       saldo_declarado: str,
                       custo_total_usdt: str | None = None) -> PlanoMovimento:
    """Validate a user intention without mutating holdings or booking a sale."""
    ativo = str(moeda).strip().upper()
    local = str(origem).strip()
    outro = str(destino).strip()
    if not ativo or not local or not outro or local.casefold() == outro.casefold():
        raise ErroMovimentoCustodia("Identifique ativo e custódias distintas.")
    if tipo not in ("transferencia", "venda"):
        raise ErroMovimentoCustodia("Tipo de movimento não suportado.")
    try:
        q = Decimal(str(quantidade))
        saldo = Decimal(str(saldo_declarado))
    except InvalidOperation as exc:
        raise ErroMovimentoCustodia("Quantidade não numérica.") from exc
    if not q.is_finite() or not saldo.is_finite() or q <= 0 or saldo < q:
        raise ErroMovimentoCustodia("Quantidade inválida ou superior ao saldo declarado.")
    try:
        d = date.fromisoformat(str(data))
    except ValueError as exc:
        raise ErroMovimentoCustodia("Data ISO inválida.") from exc
    if d > date.today():
        raise ErroMovimentoCustodia("Não registrar movimento futuro.")
    known = custo_total_usdt is not None and str(custo_total_usdt).strip() != ""
    if known:
        try:
            cost = Decimal(str(custo_total_usdt))
        except InvalidOperation as exc:
            raise ErroMovimentoCustodia("Custo não numérico.") from exc
        if not cost.is_finite() or cost < 0:
            raise ErroMovimentoCustodia("Custo documentado inválido.")
    # Sale proceeds, fees, timestamps and destination cash have not yet
    # been supplied; no monetary accounting may be inferred here.
    return PlanoMovimento(
        moeda=ativo, origem=local, destino=outro, quantidade=str(q),
        data=d.isoformat(), tipo=tipo, custo_conhecido=known,
    )
