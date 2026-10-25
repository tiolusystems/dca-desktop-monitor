"""Consulta auditável e paginada dos eventos históricos, somente leitura.

O histórico ativado é fonte de evidência; NÃO é a tabela de operações
financeiras do DCA. Cada página inclui ID, origem e natureza do impacto.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from backend.historical_activation import carregar_historico_ativo, ErroAtivacaoHistorica

FONTES = (
    "BINANCE_TRANSACOES", "BINANCE_SPOT", "MERCADO_PAGO_TRANSCRITO",
    "DIARIO_LEGADO", "CAMBIO_REAL_BINANCE", "PTAX_REFERENCIA",
)
_ATIVO = re.compile(r"^[A-Z0-9._-]{1,30}$")
_MAX_PAGINA = 100_000
_MAX_POR_PAGINA = 200


class ErroConsultaHistorica(ValueError):
    """Filtros inválidos ou fonte que não passou na conferência de integridade."""


def _data(valor, nome):
    if valor in (None, ""):
        return None
    if not isinstance(valor, str):
        raise ErroConsultaHistorica(f"{nome}: informe data AAAA-MM-DD.")
    try:
        dia = date.fromisoformat(valor)
    except ValueError as exc:
        raise ErroConsultaHistorica(f"{nome}: data inválida; use AAAA-MM-DD.") from exc
    if dia.isoformat() != valor:
        raise ErroConsultaHistorica(f"{nome}: use AAAA-MM-DD.")
    return valor


def consultar_eventos_historicos(
    diretorio_dados, *, ativo=None, fonte=None, inicio=None, fim=None,
    pagina=1, por_pagina=100,
):
    """Lê uma página da fonte SHA-verificada, sem escrever no SQLite.

    Nunca agrega execuções Spot a operações Binance, nem infere custo,
    rendimento, taxa, cotação ou patrimônio a partir de um evento isolado.
    """
    if not isinstance(pagina, int) or isinstance(pagina, bool) or not 1 <= pagina <= _MAX_PAGINA:
        raise ErroConsultaHistorica("Página fora do intervalo permitido.")
    if (not isinstance(por_pagina, int) or isinstance(por_pagina, bool)
            or not 1 <= por_pagina <= _MAX_POR_PAGINA):
        raise ErroConsultaHistorica("Quantidade por página inválida.")
    ativo = (ativo or "").strip().upper() if isinstance(ativo, (str, type(None))) else ""
    if ativo and not _ATIVO.fullmatch(ativo):
        raise ErroConsultaHistorica("Símbolo de ativo inválido.")
    fonte = (fonte or "").strip() if isinstance(fonte, (str, type(None))) else ""
    if fonte and fonte not in FONTES:
        raise ErroConsultaHistorica("Fonte documental não reconhecida.")
    inicio, fim = _data(inicio, "Data inicial"), _data(fim, "Data final")
    if inicio and fim and inicio > fim:
        raise ErroConsultaHistorica("Data inicial posterior à data final.")

    origem = carregar_historico_ativo(diretorio_dados)
    if origem is None:
        raise ErroConsultaHistorica("Nenhum histórico integral ativado.")
    pasta = Path(origem).parent
    digest = sha256(Path(origem).read_bytes()).hexdigest()
    livro = pasta / f"livro-{digest}.sqlite3"
    if livro.is_symlink() or not livro.is_file():
        raise ErroConsultaHistorica("Livro documental não encontrado.")
    clausulas, valores = [], []
    if ativo:
        clausulas.append("UPPER(ativo) = ?")
        valores.append(ativo)
    if fonte:
        clausulas.append("fonte = ?")
        valores.append(fonte)
    if inicio:
        clausulas.append("data_hora >= ?")
        valores.append(inicio + " 00:00:00")
    if fim:
        clausulas.append("data_hora <= ?")
        valores.append(fim + " 23:59:59")
    where = " WHERE " + " AND ".join(clausulas) if clausulas else ""
    sql = (
        "SELECT id_evento, data_hora, fonte, classe_evidencia, conta, ativo, "
        "quantidade_assinada, taxa_quantidade, taxa_moeda, "
        "taxa_brl_efetiva, custo_aquisicao, payload_json "
        "FROM eventos" + where + " ORDER BY data_hora DESC, id_evento DESC "
        "LIMIT ? OFFSET ?"
    )
    try:
        with closing(sqlite3.connect(livro.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            total = db.execute(
                "SELECT COUNT(*) FROM eventos" + where, valores
            ).fetchone()[0]
            resultados = db.execute(
                sql, [*valores, por_pagina, (pagina - 1) * por_pagina]
            ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise ErroConsultaHistorica("Falha na consulta somente leitura.") from exc

    eventos = []
    for row in resultados:
        (identidade, dia, origem_evento, classe, conta, moeda, quantidade,
         taxa, taxa_moeda, cambio, custo, payload_json) = row
        try:
            payload = json.loads(payload_json)
        except (ValueError, TypeError) as exc:
            raise ErroConsultaHistorica("Evento histórico com dados adulterados.") from exc
        if not isinstance(payload, dict) or payload.get("id_evento") != identidade:
            raise ErroConsultaHistorica("Evento histórico com identidade inconsistente.")
        eventos.append({
            "id_evento": identidade, "data_hora": dia,
            "fonte": origem_evento, "classe_evidencia": classe,
            "conta": conta, "ativo": moeda,
            "quantidade_assinada": quantidade, "taxa_quantidade": taxa,
            "taxa_moeda": taxa_moeda, "taxa_brl_efetiva": cambio,
            "custo_aquisicao": custo,
            "impacto_saldo": payload.get("impacto_saldo"),
            "operacao_origem": payload.get("operacao_origem"),
            "valor_brl_documentado": payload.get("valor_brl_documentado"),
            "preco_executado": payload.get("preco_executado"),
            "valor_cotacao_executado": payload.get("valor_cotacao_executado"),
            "id_ordem": payload.get("id_ordem"),
            "linha_fonte": payload.get("linha_fonte"),
            "arquivo_fonte_sha256": payload.get("arquivo_fonte_sha256"),
            "observacao": payload.get("observacao"),
        })

    # A leitura não pode expor dados se a fonte ou seu livro mudaram durante
    # a consulta. Conferência completa também detecta adulteração que preserva
    # o formato SQLite e o número de linhas.
    try:
        confirmado = carregar_historico_ativo(diretorio_dados)
    except ErroAtivacaoHistorica as exc:
        raise ErroConsultaHistorica("Integridade documental perdida durante a consulta.") from exc
    if confirmado != origem or sha256(Path(origem).read_bytes()).hexdigest() != digest:
        raise ErroConsultaHistorica("A fonte documental mudou durante a consulta.")
    return {
        "sha256": digest,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": (total + por_pagina - 1) // por_pagina,
        "filtros": {"ativo": ativo, "fonte": fonte, "inicio": inicio, "fim": fim},
        "eventos": eventos,
        "somente_leitura": True,
        "patrimonio_ou_pl_certificado": False,
    }
