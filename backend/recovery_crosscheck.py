"""Cross-check a REAL portable DCA recovery backup against documentary Binance history.

Read-only for both sources. No transactions are posted, no FX/fee/basis inferred.
"""
from __future__ import annotations
from collections import defaultdict, Counter
from contextlib import closing
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile

from backend.historical_evidence import COLUNAS, validar_historico_documental


class ErroCruzamentoHistorico(ValueError):
    pass


def _dec(value):
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ErroCruzamentoHistorico("Número financeiro inválido.") from exc
    if not x.is_finite():
        raise ErroCruzamentoHistorico("Número financeiro não finito.")
    return x


def _ler_backup(pacote):
    pacote=Path(pacote).resolve()
    if not pacote.is_file() or pacote.stat().st_size>100_000_000:
        raise ErroCruzamentoHistorico("Backup não encontrado ou excessivamente grande.")
    try:
        with zipfile.ZipFile(pacote) as z:
            from backend.recovery_bundle import ALLOWED, HIST_POINTER, HIST_FILE
            entradas=z.infolist()
            nomes={i.filename for i in entradas}
            if (len(entradas)!=len(nomes) or
                    not {"manifest.json","portfolio.sqlite3","original.csv"} <= nomes or
                    any(n not in ALLOWED and n!="manifest.json"
                        and n!=HIST_POINTER and not HIST_FILE.fullmatch(n)
                        for n in nomes) or
                    any(i.file_size>100_000_000 or i.is_dir() for i in entradas)
                    or sum(i.file_size for i in entradas)>200_000_000):
                raise ErroCruzamentoHistorico("Backup com estrutura inesperada.")
            meta=json.loads(z.read("manifest.json"))
            if (meta.get("formato")!="DCA-RECOVERY-1" or meta.get("schema")!=10
                    or not isinstance(meta.get("arquivos"),dict)
                    or nomes!=set(meta["arquivos"])|{"manifest.json"}):
                raise ErroCruzamentoHistorico("Formato/schema ou manifesto inválido.")
            for name in nomes-{"manifest.json"}:
                if sha256(z.read(name)).hexdigest()!=meta["arquivos"].get(name):
                    raise ErroCruzamentoHistorico("Backup adulterado: "+name)
            evidencias={n for n in nomes if n.startswith("evidencias/")}
            if evidencias:
                if HIST_POINTER not in evidencias:
                    raise ErroCruzamentoHistorico("Backup com histórico sem marcador ativo.")
                marcador=json.loads(z.read(HIST_POINTER))
                digest=marcador.get("sha256")
                if not isinstance(digest,str) or len(digest)!=64 or any(
                        c not in "0123456789abcdef" for c in digest):
                    raise ErroCruzamentoHistorico("SHA do histórico de backup inválido.")
                esperado={HIST_POINTER,
                          f"evidencias/historico-{digest}.csv",
                          f"evidencias/historico-{digest}.json"}
                if evidencias!=esperado or sha256(z.read(
                        f"evidencias/historico-{digest}.csv")).hexdigest()!=digest:
                    raise ErroCruzamentoHistorico("Histórico documental do backup incompleto.")
            db_bytes=z.read("portfolio.sqlite3")
            csv_bytes=z.read("original.csv")
    except (zipfile.BadZipFile,OSError,KeyError,ValueError,
            json.JSONDecodeError) as exc:
        raise ErroCruzamentoHistorico("Pacote de recuperação inválido.") from exc
    with tempfile.TemporaryDirectory(prefix="dca-recovery-audit-") as tmp:
        dbfile=Path(tmp)/"readonly.sqlite3"
        dbfile.write_bytes(db_bytes)
        try:
            with closing(sqlite3.connect(dbfile.resolve().as_uri()+"?mode=ro",
                                         uri=True)) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                    raise ErroCruzamentoHistorico("SQLite inválido.")
                if db.execute("PRAGMA user_version").fetchone()[0]!=10:
                    raise ErroCruzamentoHistorico("SQLite schema incompatível.")
                found=db.execute("SELECT uuid FROM identidade_carteira WHERE id=1").fetchone()
                if not found or found[0]!=meta.get("uuid"):
                    raise ErroCruzamentoHistorico("Identidade da carteira divergente.")
                cur=db.execute(
                    "SELECT id,data,moeda,operacao,valor_usdt,preco,quantidade "
                    "FROM operacoes ORDER BY id")
                linhas=[dict(zip((x[0] for x in cur.description),row))
                        for row in cur.fetchall()]
                saldos_iniciais=db.execute(
                    "SELECT COUNT(*) FROM posicoes_iniciais").fetchone()[0]
                externos=db.execute(
                    "SELECT COUNT(*) FROM posicoes_externas").fetchone()[0]
                custodias=db.execute(
                    "SELECT COUNT(*) FROM movimentacoes_custodia").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise ErroCruzamentoHistorico("Estrutura do SQLite inválida.") from exc
    try:
        original=list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")),
                                     strict=True))
    except (UnicodeError,csv.Error) as exc:
        raise ErroCruzamentoHistorico("CSV original inválido.") from exc
    if len(original)!=len(linhas):
        raise ErroCruzamentoHistorico("Original CSV não corresponde ao banco.")
    divergencias=0
    for a,b in zip(linhas,original):
        try:
            igual=(a["moeda"]==b["Moeda"] and a["operacao"]==b["Operacao"]
                   and datetime.strptime(a["data"],"%Y-%m-%d %H:%M:%S")
                       ==datetime.strptime(b["Data"],"%Y-%m-%d %H:%M:%S")
                   and _dec(a["valor_usdt"])==_dec(b["Valor_USDT"])
                   and _dec(a["quantidade"])==_dec(b["Quantidade"]))
        except (KeyError,ValueError,TypeError) as exc:
            raise ErroCruzamentoHistorico("CSV original malformado.") from exc
        divergencias+=int(not igual)
    return {
        "operacoes":linhas,"hash_original":sha256(csv_bytes).hexdigest(),
        "hash_sqlite":sha256(db_bytes).hexdigest(),
        "hash_pacote":sha256(pacote.read_bytes()).hexdigest(),
        "divergencias_original":divergencias,
        "saldos_iniciais":saldos_iniciais,
        "posicoes_externas":externos,
        "movimentos_custodia":custodias,
    }


def auditar_backup_e_historico(pacote, historico):
    """Compare by order, base asset, side, price, quantity and gross values.

    1% is a CANDIDATE search bound, never a permission to correct or mutate.
    Ties remain unconfirmed. Unique matches remain proposals for review.
    """
    info=validar_historico_documental(Path(historico))
    backup=_ler_backup(pacote)
    fontes=Counter()
    legacy={}
    spot=defaultdict(list)
    with Path(historico).open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f,strict=True):
            fonte=row["fonte"]
            fontes[fonte]+=1
            if fonte=="DIARIO_LEGADO":
                legacy[int(row["linha_fonte"])-1]=row
            elif fonte=="BINANCE_SPOT":
                if row["classe_evidencia"]!="EXECUCAO_SPOT" or not row["id_ordem"]:
                    raise ErroCruzamentoHistorico("Execução Spot sem ordem.")
                spot[(row["id_ordem"],row["par"],row["lado"])].append(row)
    if len(legacy)!=len(backup["operacoes"]) or not fontes["BINANCE_TRANSACOES"]:
        raise ErroCruzamentoHistorico("Histórico não corresponde ao diário ou à Binance.")
    for numero,operation in enumerate(backup["operacoes"],1):
        row=legacy.get(numero)
        if row is None or (row["data_hora"]!=operation["data"]
                          or row["ativo"]!=operation["moeda"]
                          or row["operacao_origem"]!=operation["operacao"]
                          or _dec(row["quantidade_assinada"])!=_dec(operation["quantidade"])):
            raise ErroCruzamentoHistorico("Diário documental não corresponde ao SQLite.")

    ordens=[]
    for (oid,par,lado),fills in spot.items():
        qt=sum((_dec(f["quantidade_executada"]) for f in fills),Decimal(0))
        vl=sum((_dec(f["valor_cotacao_executado"]) for f in fills),Decimal(0))
        fees=defaultdict(Decimal)
        for fill in fills:
            if fill["taxa_quantidade"]:
                fees[fill["taxa_moeda"]]+=_dec(fill["taxa_quantidade"])
        first=min(f["data_hora"] for f in fills)
        ordens.append({
            "id_ordem":oid,"par":par,"lado":lado,"moeda_cotacao":fills[0]["moeda_cotacao"],
            "ativo":fills[0]["ativo"],"quantidade":qt,"valor_bruto":vl,
            "taxas":dict(fees),"data":first,
        })

    encontrados=set()
    comparacoes=[]
    for op in backup["operacoes"]:
        candidatos=[]
        if op["moeda"] not in ("USDT","USDC"):
            data=datetime.strptime(op["data"],"%Y-%m-%d %H:%M:%S")
            lado="BUY" if op["operacao"]=="compra" else "SELL"
            for ordem in ordens:
                if (ordem["id_ordem"] in encontrados
                    or ordem["ativo"]!=op["moeda"] or ordem["lado"]!=lado
                    or ordem["data"][:4]!=op["data"][:4]
                    or ordem["quantidade"]<=0 or ordem["valor_bruto"]<=0):
                    continue
                qdist=abs(ordem["quantidade"]-_dec(op["quantidade"]))/ordem["quantidade"]
                vdist=abs(ordem["valor_bruto"]-_dec(op["valor_usdt"]))/ordem["valor_bruto"]
                preco=ordem["valor_bruto"]/ordem["quantidade"]
                pdist=abs(preco-_dec(op["preco"]))/preco
                if any(x>=Decimal("0.01") for x in (qdist,vdist,pdist)):
                    continue
                seconds=abs((datetime.strptime(ordem["data"],"%Y-%m-%d %H:%M:%S")
                             -data).total_seconds())
                nota=qdist+vdist+pdist+Decimal(str(seconds))/Decimal(315360000000)
                candidatos.append((nota,ordem))
        candidatos.sort(key=lambda x:x[0])
        encontrado=None
        status="SEM_ORDEM_SPOT_COMPROVADA"
        if candidatos and (len(candidatos)==1
                           or candidatos[1][0]-candidatos[0][0]>=Decimal("0.00001")):
            encontrado=candidatos[0][1]
            encontrados.add(encontrado["id_ordem"])
            status=("CONCILIADO_USDT" if encontrado["moeda_cotacao"]=="USDT"
                    else "COTADO_OUTRA_MOEDA")
        elif candidatos:
            status="AMBIGUO_NAO_AUTOCORRIGIR"
        comparacoes.append({
            "id_sqlite":str(op["id"]),"data_dca":op["data"],
            "ativo":op["moeda"],"operacao":op["operacao"],
            "status":status,
            "id_ordem_binance":encontrado["id_ordem"] if encontrado else "",
            "par_real":encontrado["par"] if encontrado else "",
            "data_execucao_real":encontrado["data"] if encontrado else "",
            "moeda_cotacao_real":encontrado["moeda_cotacao"] if encontrado else "",
            "quantidade_antiga":op["quantidade"],
            "quantidade_real":str(encontrado["quantidade"]) if encontrado else "",
            "valor_antigo_usdt_nominal":op["valor_usdt"],
            "valor_real_moeda_cotacao":str(encontrado["valor_bruto"]) if encontrado else "",
            "taxas_reais_por_moeda":(
                "; ".join(f"{v} {k}" for k,v in sorted(encontrado["taxas"].items()))
                if encontrado else ""),
        })
    ausentes=[o for o in ordens if o["id_ordem"] not in encontrados]
    return {
        "backup":{k:v for k,v in backup.items() if k!="operacoes"},
        "historico_sha256":info["sha256"],"fontes":dict(fontes),
        "operacoes_sqlite":len(backup["operacoes"]),"ordens_spot":len(ordens),
        "correspondencias":len(encontrados),"ordens_spot_ausentes":len(ausentes),
        "ordens_2026_ausentes":sum(x["data"].startswith("2026-") for x in ausentes),
        "sem_spot":sum(x["status"]=="SEM_ORDEM_SPOT_COMPROVADA" for x in comparacoes),
        "cotadas_nao_usdt":sum(x["status"]=="COTADO_OUTRA_MOEDA" for x in comparacoes),
        "comparacoes":comparacoes,"ordens_ausentes":[{
            "id_ordem":x["id_ordem"],"data":x["data"],"par":x["par"],
            "lado":x["lado"],"quantidade":str(x["quantidade"]),
            "valor_bruto":str(x["valor_bruto"]),
            "moeda_cotacao":x["moeda_cotacao"],
            "taxas_por_moeda":{k:str(v) for k,v in x["taxas"].items()},
        } for x in ausentes],
        "financeiro_alterado":False,"status":"AUDITORIA_NAO_E_MIGRACAO",
    }


def exportar_comparacao(resultado,destino):
    destino=Path(destino)
    if destino.exists():
        raise ErroCruzamentoHistorico("Relatório existente; não sobrescrever.")
    linhas=resultado["comparacoes"]
    if not linhas:
        raise ErroCruzamentoHistorico("Não há operações para exportar.")
    with destino.open("x",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(linhas[0]))
        writer.writeheader()
        writer.writerows(linhas)
    return str(destino)
