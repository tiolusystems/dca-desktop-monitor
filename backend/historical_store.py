"""Livro documental SQLite separado da carteira operacional do DCA.

Cada linha auditada é preservada com origem e JSON integral. Não cria
compras fictícias, não converte PTAX para USDT, não altera portfolio.sqlite3.
"""
from __future__ import annotations

import csv
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from itertools import zip_longest
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from backend.historical_evidence import validar_historico_documental
from backend.historical_reconciliation import reconciliar_historico_documental

VERSAO = 1


class ErroLivroDocumental(ValueError):
    pass


def _verificar_livro(arquivo: Path, hash_fonte: str, quantidade: int,
                    fonte: Path | None = None) -> bool:
    """Fail closed on SQLite corruption AND valid-SQLite content manipulation.

    PRAGMA integrity_check only checks B-tree structure, not that stored
    transactions and custody totals match the immutable, SHA-pinned CSV.
    """
    try:
        with closing(sqlite3.connect(arquivo.resolve().as_uri()+"?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return False
            meta = db.execute(
                "SELECT sha256_fonte, quantidade_eventos, versao, marcador FROM manifesto"
            ).fetchall()
            if meta != [(hash_fonte, quantidade, VERSAO,
                         "DOCUMENTAL_NAO_SUBSTITUI_FINANCEIRO")]:
                return False
            count = db.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
            if count != quantidade:
                return False
            if fonte is None:
                return True

            fonte = Path(fonte)
            if sha256(fonte.read_bytes()).hexdigest() != hash_fonte:
                return False
            campos = (
                "id_evento", "data_hora", "fonte", "classe_evidencia", "conta",
                "ativo", "quantidade_assinada", "taxa_quantidade", "taxa_moeda",
                "taxa_brl_efetiva", "custo_aquisicao",
            )
            sql = db.execute(
                "SELECT " + ", ".join(campos) +
                ", payload_json FROM eventos ORDER BY id_evento"
            )
            with fonte.open(encoding="utf-8-sig", newline="") as arquivo_csv:
                expected_rows = sorted(
                    csv.DictReader(arquivo_csv, strict=True),
                    key=lambda item: item["id_evento"],
                )
            for original, armazenado in zip_longest(expected_rows, sql):
                if original is None or armazenado is None:
                    return False
                expected = tuple(original[k] for k in campos) + (
                    json.dumps(original, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")),
                )
                if armazenado != expected:
                    return False

            # Verify that derived custody balances were not altered either.
            # A modified SQLite can pass PRAGMA integrity_check and row counts.
            previa = reconciliar_historico_documental(fonte)
            expected_saldos = sorted(
                (row["custodia"], row["ativo"], row["saldo_algebrico"],
                 row["menor_saldo_no_periodo"], row["status"], None)
                for row in previa["saldos"]
            )
            saldos = db.execute(
                "SELECT custodia, ativo, saldo_algebrico, menor_saldo, status, "
                "custo_brl FROM saldos_documentais ORDER BY custodia, ativo"
            ).fetchall()
            return saldos == expected_saldos
    except (sqlite3.DatabaseError, OSError, UnicodeError, csv.Error,
            ValueError, KeyError, TypeError):
        return False


def construir_livro_documental(origem: Path, diretorio_dados: Path) -> dict:
    """Materializa um livro de evidências imutável POR SHA em outro arquivo.

    Não substitui, abre ou escreve o SQLite financeiro operacional.
    Uma fonte alterada entre validação e consolidação é recusada.
    """
    fonte=Path(origem).expanduser().resolve()
    dados=validar_historico_documental(fonte)
    previa=reconciliar_historico_documental(fonte)
    if previa["sha256"]!=dados["sha256"]:
        raise ErroLivroDocumental("Fonte mudou durante conciliação.")
    pasta=Path(diretorio_dados).expanduser().resolve()/"evidencias"
    pasta.mkdir(parents=True,exist_ok=True)
    destino=pasta/f'livro-{dados["sha256"]}.sqlite3'
    carteira=(Path(diretorio_dados).expanduser().resolve()/"portfolio.sqlite3")
    if destino.resolve()==carteira:
        raise ErroLivroDocumental("Recusada substituição do SQLite financeiro.")
    if destino.exists():
        if not _verificar_livro(destino,dados["sha256"],dados["quantidade"],fonte=fonte):
            raise ErroLivroDocumental("Livro documental existente inválido; não sobrescrever.")
        return {"arquivo":str(destino),"eventos":dados["quantidade"],
                "sha256_fonte":dados["sha256"],"ja_existia":True,
                "sqlite_financeiro_alterado":False,
                "pendencias":previa["negativos_finais"]}
    fd,temp=tempfile.mkstemp(prefix=".livro-dca-",suffix=".sqlite3",dir=pasta)
    os.close(fd)
    temp=Path(temp)
    try:
        with closing(sqlite3.connect(temp)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(
                "CREATE TABLE manifesto ("
                "sha256_fonte TEXT NOT NULL, quantidade_eventos INTEGER NOT NULL,"
                "versao INTEGER NOT NULL, criado_em_utc TEXT NOT NULL,"
                "marcador TEXT NOT NULL);"
                "CREATE TABLE eventos ("
                "id_evento TEXT PRIMARY KEY,data_hora TEXT NOT NULL,"
                "fonte TEXT NOT NULL, classe_evidencia TEXT NOT NULL,"
                "conta TEXT NOT NULL, ativo TEXT NOT NULL,"
                "quantidade_assinada TEXT, taxa_quantidade TEXT, taxa_moeda TEXT,"
                "taxa_brl_efetiva TEXT, custo_aquisicao TEXT,"
                "payload_json TEXT NOT NULL);"
                "CREATE INDEX ix_eventos_data ON eventos (data_hora,fonte);"
                "CREATE INDEX ix_eventos_ativo ON eventos (conta,ativo);"
                "CREATE TABLE saldos_documentais ("
                "custodia TEXT NOT NULL,ativo TEXT NOT NULL,"
                "saldo_algebrico TEXT NOT NULL,menor_saldo TEXT NOT NULL,"
                "status TEXT NOT NULL,custo_brl TEXT,"
                "PRIMARY KEY(custodia,ativo));"
            )
            db.execute("INSERT INTO manifesto VALUES(?,?,?,?,?)",(
                dados["sha256"],dados["quantidade"],VERSAO,
                datetime.now(timezone.utc).isoformat(),"DOCUMENTAL_NAO_SUBSTITUI_FINANCEIRO"))
            contagem=0
            with fonte.open(encoding="utf-8-sig",newline="") as fp:
                for row in csv.DictReader(fp):
                    db.execute("INSERT INTO eventos VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(
                        row["id_evento"],row["data_hora"],row["fonte"],
                        row["classe_evidencia"],row["conta"],row["ativo"],
                        row["quantidade_assinada"],row["taxa_quantidade"],
                        row["taxa_moeda"],row["taxa_brl_efetiva"],row["custo_aquisicao"],
                        json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(",",":")),
                    ))
                    contagem+=1
            if contagem!=dados["quantidade"]:
                raise ErroLivroDocumental("Número de eventos mudou; abortado.")
            for saldo in previa["saldos"]:
                db.execute("INSERT INTO saldos_documentais VALUES(?,?,?,?,?,?)",(
                    saldo["custodia"],saldo["ativo"],saldo["saldo_algebrico"],
                    saldo["menor_saldo_no_periodo"],saldo["status"],
                    None,  # Desconhecido é NULL, jamais custo zero.
                ))
            if sha256(fonte.read_bytes()).hexdigest()!=dados["sha256"]:
                raise ErroLivroDocumental("CSV alterado durante a escrituração; abortado.")
            db.commit()
        if not _verificar_livro(temp,dados["sha256"],dados["quantidade"],fonte=fonte):
            raise ErroLivroDocumental("Livro gerado falhou na conferência de integridade.")
        # Não usar replace() para sobrescrever cópia anterior: link exclusivo,
        # mesma partição, falha caso arquivo alvo já exista (idempotência).
        try:
            os.link(temp,destino)
        except FileExistsError:
            if not _verificar_livro(destino,dados["sha256"],dados["quantidade"],fonte=fonte):
                raise ErroLivroDocumental("Conflito na criação do livro documental.")
        if not _verificar_livro(destino,dados["sha256"],dados["quantidade"],fonte=fonte):
            raise ErroLivroDocumental("Livro final não passou na verificação.")
    finally:
        temp.unlink(missing_ok=True)
    return {
        "arquivo":str(destino),"eventos":dados["quantidade"],
        "sha256_fonte":dados["sha256"],"ja_existia":False,
        "sqlite_financeiro_alterado":False,
        "pendencias":previa["negativos_finais"],
    }
