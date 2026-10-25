"""Ativação do histórico completo como fonte de consulta do DCA.

O banco de patrimônio existente é INVOLÁVEL: a ativação grava somente arquivos
novos em <dados>/evidencias e uma referência atômica a um CSV verificado.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

from backend.historical_evidence import (
    validar_historico_documental, arquivar_historico_documental,
    _verificar_manifesto_arquivado,
)
from backend.historical_store import construir_livro_documental, _verificar_livro


class ErroAtivacaoHistorica(ValueError):
    pass


SCHEMA = 1
SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _pasta(diretorio_dados):
    return Path(diretorio_dados).expanduser().resolve() / "evidencias"


def carregar_historico_ativo(diretorio_dados):
    """Retorna o CSV completo ou None; falha fechada para fonte adulterada."""
    pasta = _pasta(diretorio_dados)
    pointer = pasta / "historico-ativo.json"
    if not pointer.exists():
        return None
    try:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        chave = payload["sha256"]
        if payload.get("schema") != SCHEMA or not isinstance(chave, str) or not SHA_PATTERN.fullmatch(chave):
            raise ErroAtivacaoHistorica("Marcador de histórico ativo inválido.")
        expected = f"historico-{chave}.csv"
        if payload.get("arquivo") != expected or not isinstance(payload.get("eventos"), int):
            raise ErroAtivacaoHistorica("Identidade de arquivo ou contagem inválida.")
        caminho = pasta / expected
        livro = pasta / f"livro-{chave}.sqlite3"
        if caminho.is_symlink() or livro.is_symlink() or not caminho.is_file():
            raise ErroAtivacaoHistorica("Arquivo documental não encontrado ou não confiável.")
        if sha256(caminho.read_bytes()).hexdigest() != chave:
            raise ErroAtivacaoHistorica("Histórico documental modificado após a ativação.")
        if not livro.is_file() or not _verificar_livro(livro, chave, payload["eventos"], fonte=caminho):
            raise ErroAtivacaoHistorica("Livro histórico ausente ou com integridade inválida.")
        # A fonte só é ativa se seu manifesto documental também continuar
        # íntegro. Um JSON editado após a importação não pode ser ignorado.
        _verificar_manifesto_arquivado(
            pasta / f"historico-{chave}.json",
            validar_historico_documental(caminho),
        )
        return caminho
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, ErroAtivacaoHistorica):
            raise
        raise ErroAtivacaoHistorica("Não foi possível verificar o histórico ativo.") from exc


def ativar_historico_documental(origem, diretorio_dados, *, sha_confirmado):
    """Ativa somente após validar/capturar SHA e criar o livro íntegro.

    Incompletude histórica NÃO impede importação para consulta, mas bloqueia
    avaliação integral e apuração de lucro. NÃO grava em portfolio.sqlite3.
    """
    origem = Path(origem).expanduser().resolve()
    pasta = _pasta(diretorio_dados)
    dados = validar_historico_documental(origem)
    if dados["sha256"] != sha_confirmado:
        raise ErroAtivacaoHistorica("O CSV mudou desde a conferência.")
    if not dados["fontes"].get("BINANCE_TRANSACOES"):
        raise ErroAtivacaoHistorica("Não há movimentações Binance no documento.")
    copia = arquivar_historico_documental(origem, diretorio_dados, sha_confirmado)
    livro = construir_livro_documental(Path(copia["copia"]), diretorio_dados)
    if livro["sha256_fonte"] != dados["sha256"] or livro["eventos"] != dados["quantidade"]:
        raise ErroAtivacaoHistorica("Livro documental divergente; ativação cancelada.")
    arquivo = f'historico-{dados["sha256"]}.csv'
    ponteiro = {
        "schema": SCHEMA, "arquivo": arquivo,
        "sha256": dados["sha256"], "eventos": dados["quantidade"],
        "status": "HISTORICO_DOCUMENTAL_NAO_CERTIFICADO",
    }
    pasta.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", dir=pasta, prefix=".historico-ativo-",
                suffix=".tmp", encoding="utf-8", delete=False) as out:
            tmp = Path(out.name)
            json.dump(ponteiro, out, sort_keys=True, ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, pasta / "historico-ativo.json")
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    if carregar_historico_ativo(diretorio_dados) != pasta / arquivo:
        raise ErroAtivacaoHistorica("Ponteiro de histórico não passou na conferência.")
    return {
        "arquivo_ativo": str(pasta / arquivo), "eventos": dados["quantidade"],
        "fontes": dados["fontes"], "sha256": dados["sha256"],
        "livro": livro["arquivo"],
        "pendencias_custodia": livro["pendencias"],
        "sqlite_operacional_alterado": False,
    }
