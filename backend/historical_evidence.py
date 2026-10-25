"""Histórico documental: importa evidência para arquivo SEPARADO, sem mexer na carteira.

O CSV integral traz movimentos de conta Binance, execuções Spot, transcrição MP
e diário legado como fontes distintas. Nunca soma as camadas duplicadas como
compras ou patrimônio. Sem câmbio/taxa/custo comprovados, permanece desconhecido.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import tempfile

COLUNAS = (
    "id_evento", "data_hora", "fonte", "arquivo_fonte_sha256", "linha_fonte",
    "classe_evidencia", "impacto_saldo", "conta", "operacao_origem", "ativo",
    "quantidade_assinada", "valor_brl_documentado", "moeda_cotacao", "par",
    "lado", "preco_executado", "quantidade_executada", "valor_cotacao_executado",
    "taxa_quantidade", "taxa_moeda", "id_ordem", "taxa_brl_efetiva",
    "ptax_usd_brl_referencia", "custo_aquisicao", "identificador_vinculo",
    "observacao",
)
TIPOS_IMPACTO = {
    "SIM_APENAS_SALDO_CONTA_DOCUMENTADA",
    "NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE",
    "SOMENTE_CUSTODIA_MERCADO_PAGO_NAO_ADICIONAR_A_BINANCE",
    "NAO_SOMAR_ORIGEM_NAO_VERIFICADA",
    "NENHUM",
}
CAMPOS_NUMERICOS = (
    "quantidade_assinada", "valor_brl_documentado", "preco_executado",
    "quantidade_executada", "valor_cotacao_executado", "taxa_quantidade",
    "taxa_brl_efetiva", "ptax_usd_brl_referencia",
)
LIMITE_BYTES = 25_000_000
LIMITE_REGISTROS = 200_000
REGEX_SHA = re.compile(r"^[a-f0-9]{64}$")
REGEX_ID = re.compile(r"^[a-f0-9]{24}$")


class ErroHistoricoDocumental(ValueError):
    """Recusa documento incorreto sem alterar dados financeiros."""


def _inteiro_positivo(valor: str, linha: int) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise ErroHistoricoDocumental(f"Linha {linha}: índice de origem inválido.") from exc
    if numero < 2:
        raise ErroHistoricoDocumental(f"Linha {linha}: índice de origem inválido.")
    return numero


def _validar_evento(linha: dict, numero: int) -> None:
    if None in linha or set(linha) != set(COLUNAS):
        raise ErroHistoricoDocumental(f"Linha {numero}: número de colunas incorreto.")
    if not REGEX_ID.fullmatch(linha["id_evento"] or ""):
        raise ErroHistoricoDocumental(f"Linha {numero}: ID inválido.")
    if not REGEX_SHA.fullmatch(linha["arquivo_fonte_sha256"] or ""):
        raise ErroHistoricoDocumental(f"Linha {numero}: SHA da fonte inválido.")
    if linha["impacto_saldo"] not in TIPOS_IMPACTO:
        raise ErroHistoricoDocumental(f"Linha {numero}: classificação de impacto inválida.")
    try:
        data = datetime.strptime(linha["data_hora"], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError) as exc:
        raise ErroHistoricoDocumental(f"Linha {numero}: data inválida.") from exc
    if not 2009 <= data.year <= 2100:
        raise ErroHistoricoDocumental(f"Linha {numero}: data fora do intervalo.")
    if not linha["fonte"] or not linha["classe_evidencia"]:
        raise ErroHistoricoDocumental(f"Linha {numero}: fonte ou classe ausente.")
    idx = _inteiro_positivo(linha["linha_fonte"], numero)
    # Identidade verificável e estável: duplicação documental é detectada.
    esperado = sha256((
        f'{linha["fonte"]}:{linha["arquivo_fonte_sha256"]}:'
        f'{idx}:{linha["classe_evidencia"]}:{linha["data_hora"]}'
    ).encode()).hexdigest()[:24]
    if linha["id_evento"] != esperado:
        raise ErroHistoricoDocumental(f"Linha {numero}: ID de evidência não confere.")
    for campo in CAMPOS_NUMERICOS:
        bruto = linha[campo]
        if bruto:
            try:
                valor = Decimal(bruto)
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ErroHistoricoDocumental(f"Linha {numero}: {campo} inválido.") from exc
            if not valor.is_finite():
                raise ErroHistoricoDocumental(f"Linha {numero}: {campo} não finito.")
            if campo == "taxa_quantidade" and valor < 0:
                raise ErroHistoricoDocumental(f"Linha {numero}: taxa negativa.")
    if bool(linha["taxa_quantidade"]) != bool(linha["taxa_moeda"]):
        raise ErroHistoricoDocumental(f"Linha {numero}: taxa sem moeda ou vice-versa.")
    if linha["classe_evidencia"] == "EXECUCAO_SPOT":
        if not all(linha[k] for k in ("id_ordem", "par", "lado", "quantidade_executada", "valor_cotacao_executado")):
            raise ErroHistoricoDocumental(f"Linha {numero}: execução Spot incompleta.")
        if linha["impacto_saldo"] != "NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE":
            raise ErroHistoricoDocumental(f"Linha {numero}: execução poderia duplicar saldo.")
    if linha["fonte"] == "BINANCE_TRANSACOES" and linha["impacto_saldo"] != "SIM_APENAS_SALDO_CONTA_DOCUMENTADA":
        raise ErroHistoricoDocumental(f"Linha {numero}: impacto Binance incompatível.")
    if linha["classe_evidencia"] == "TRANSFERENCIA_BTC_EXTERNA_TRANSCRITA":
        if linha["operacao_origem"] != "transferência enviada":
            raise ErroHistoricoDocumental(f"Linha {numero}: transferência reclassificada.")
    if linha["fonte"] == "PTAX_REFERENCIA" and linha["taxa_brl_efetiva"]:
        raise ErroHistoricoDocumental(f"Linha {numero}: PTAX não é câmbio executado.")
    # HIST-07: a classificação não pode contradizer a fonte que o
    # reconciliador realmente contabiliza. Antes, um evento MP marcado
    # "NENHUM" ainda entrava no saldo, e um SPOT com classe arbitrária
    # podia ser contado como comprovante de compra BRL.
    fonte = linha["fonte"]
    classe = linha["classe_evidencia"]
    impacto = linha["impacto_saldo"]
    if fonte == "BINANCE_SPOT":
        if classe != "EXECUCAO_SPOT" or impacto != "NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE":
            raise ErroHistoricoDocumental(
                f"Linha {numero}: fonte Spot incompatível com classe/impacto.")
        if linha["lado"].upper() not in ("BUY", "SELL"):
            raise ErroHistoricoDocumental(f"Linha {numero}: lado Spot inválido.")
    elif fonte == "MERCADO_PAGO_TRANSCRITO":
        if impacto != "SOMENTE_CUSTODIA_MERCADO_PAGO_NAO_ADICIONAR_A_BINANCE":
            raise ErroHistoricoDocumental(
                f"Linha {numero}: fonte Mercado Pago incompatível com impacto.")
        bruto = linha["quantidade_assinada"]
        if not bruto:
            raise ErroHistoricoDocumental(
                f"Linha {numero}: quantidade Mercado Pago ausente.")
        qtd = Decimal(bruto)
        if classe == "TRANSFERENCIA_BTC_EXTERNA_TRANSCRITA" and qtd >= 0:
            raise ErroHistoricoDocumental(
                f"Linha {numero}: transferência enviada deve reduzir a custódia.")
        if classe == "COMPRA_BTC_BRL_TRANSCRITA" and qtd <= 0:
            raise ErroHistoricoDocumental(
                f"Linha {numero}: compra MP deve aumentar a custódia.")
        if classe == "VENDA_BTC_BRL_TRANSCRITA" and qtd >= 0:
            raise ErroHistoricoDocumental(
                f"Linha {numero}: venda MP deve reduzir a custódia.")
    elif fonte != "BINANCE_TRANSACOES" and impacto in (
        "SIM_APENAS_SALDO_CONTA_DOCUMENTADA",
        "SOMENTE_CUSTODIA_MERCADO_PAGO_NAO_ADICIONAR_A_BINANCE",
    ):
        raise ErroHistoricoDocumental(
            f"Linha {numero}: fonte documental sem autorização de impacto no saldo.")
    if fonte == "CAMBIO_REAL_BINANCE" and (
        not linha["taxa_brl_efetiva"]
        or Decimal(linha["taxa_brl_efetiva"]) <= 0
    ):
        raise ErroHistoricoDocumental(
            f"Linha {numero}: câmbio executado ausente ou não positivo.")



def validar_historico_documental(origem: Path) -> dict:
    """Prévia somente leitura: nenhum SQLite é aberto ou alterado."""
    caminho = Path(origem).expanduser().resolve()
    if not caminho.is_file() or caminho.stat().st_size > LIMITE_BYTES:
        raise ErroHistoricoDocumental("CSV documental inexistente ou excessivamente grande.")
    bruto = caminho.read_bytes()
    try:
        texto = bruto.decode("utf-8-sig")
        leitor = csv.DictReader(io.StringIO(texto, newline=""), strict=True)
        if tuple(leitor.fieldnames or ()) != COLUNAS:
            raise ErroHistoricoDocumental("Cabeçalho documental incompatível; não é CSV legado.")
        fontes = Counter()
        classes = Counter()
        impactos = Counter()
        identificadores = set()
        hashes_fonte = {}
        quantidade = 0
        for numero, linha in enumerate(leitor, 2):
            quantidade += 1
            if quantidade > LIMITE_REGISTROS:
                raise ErroHistoricoDocumental("Limite de linhas documentais excedido.")
            _validar_evento(linha, numero)
            identidade = linha["id_evento"]
            if identidade in identificadores:
                raise ErroHistoricoDocumental(f"Linha {numero}: evento duplicado.")
            identificadores.add(identidade)
            origem_nome = linha["fonte"]
            sha = linha["arquivo_fonte_sha256"]
            if origem_nome in hashes_fonte and hashes_fonte[origem_nome] != sha:
                raise ErroHistoricoDocumental(f"Linha {numero}: fonte mudou de SHA.")
            hashes_fonte[origem_nome] = sha
            fontes[origem_nome] += 1
            classes[linha["classe_evidencia"]] += 1
            impactos[linha["impacto_saldo"]] += 1
    except (UnicodeError, csv.Error) as exc:
        raise ErroHistoricoDocumental(f"CSV documental inválido: {exc}") from exc
    if not quantidade:
        raise ErroHistoricoDocumental("CSV documental sem eventos.")
    return {
        "arquivo": str(caminho), "sha256": sha256(bruto).hexdigest(),
        "quantidade": quantidade, "fontes": dict(fontes),
        "classes": dict(classes), "impactos": dict(impactos),
        "sha256_fontes_declarados": hashes_fonte,
        "escritura_financeira_alterada": False,
        "aviso": (
            "Este arquivo é evidência auditável, NÃO operações para somar novamente. "
            "Movimentos internos, taxas nativas e custos sem origem conhecida "
            "exigem conciliação antes de alimentar patrimônio e P/L."
        ),
    }


def _verificar_manifesto_arquivado(meta: Path, info: dict) -> None:
    """Reject an altered evidence manifest, including valid-JSON tampering.

    The original import path is not part of the evidence identity: importing
    identical bytes from a different folder must remain idempotent. All other
    fields must match a fresh, SHA-verified parse of the archived CSV.
    """
    if meta.is_symlink() or not meta.is_file():
        raise ErroHistoricoDocumental("Manifesto de evidência ausente ou não confiável.")
    try:
        if meta.stat().st_size > 1_000_000:
            raise ErroHistoricoDocumental("Manifesto de evidência excessivamente grande.")
        declarado = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ErroHistoricoDocumental("Manifesto de evidência ilegível ou inválido.") from exc
    if not isinstance(declarado, dict) or set(declarado) != set(info):
        raise ErroHistoricoDocumental("Manifesto de evidência com estrutura adulterada.")
    if any(declarado[k] != v for k, v in info.items() if k != "arquivo"):
        raise ErroHistoricoDocumental("Manifesto não corresponde ao CSV original verificado.")


def arquivar_historico_documental(origem: Path, diretorio_dados: Path, sha_esperado: str) -> dict:
    """Arquiva cópia imutável verificável, fora do SQLite operacional.

    Diretório de dados NÃO deve apontar para local de instalação.
    Exige confirmação do SHA da prévia; não substitui arquivo preexistente.
    """
    info = validar_historico_documental(origem)
    if info["sha256"] != sha_esperado:
        raise ErroHistoricoDocumental("O CSV mudou desde a prévia; operação cancelada.")
    pasta = Path(diretorio_dados).expanduser().resolve() / "evidencias"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f'historico-{info["sha256"]}.csv'
    meta = pasta / f'historico-{info["sha256"]}.json'
    if destino.is_symlink():
        raise ErroHistoricoDocumental("Arquivo de evidência não pode ser um link simbólico.")
    # Never follow a pre-existing manifest symlink or silently accept a
    # replaced JSON whose SHA/count/source summaries contradict the CSV.
    if meta.is_symlink():
        raise ErroHistoricoDocumental("Manifesto não pode ser um link simbólico.")
    if meta.exists():
        _verificar_manifesto_arquivado(meta, info)
    ja_arquivado = destino.exists()
    if ja_arquivado and sha256(destino.read_bytes()).hexdigest() != info["sha256"]:
        raise ErroHistoricoDocumental("Arquivo anterior foi alterado; não sobrescrever.")

    # HIST-10: o CSV não pode ficar truncado caso o aplicativo seja fechado,
    # o disco encha ou a energia caia durante a cópia. Escrever e fsync em
    # arquivo temporário; só publicar via hard link exclusivo após conferir
    # integralmente o SHA. A operação nunca sobrescreve uma evidência.
    temporario = None
    temp_meta = None
    try:
        if not ja_arquivado:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".historico-", dir=pasta, delete=False,
            ) as stream:
                temporario = Path(stream.name)
                stream.write(Path(origem).read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            if sha256(temporario.read_bytes()).hexdigest() != info["sha256"]:
                raise ErroHistoricoDocumental("Verificação de cópia falhou.")
            try:
                os.link(temporario, destino)
            except FileExistsError:
                # Duas ativações simultâneas do mesmo documento são idempotentes.
                if destino.is_symlink() or sha256(destino.read_bytes()).hexdigest() != info["sha256"]:
                    raise ErroHistoricoDocumental("Conflito de evidência; não sobrescrever.")
                ja_arquivado = True
        # Pode ter havido falha após publicar CSV e antes de criar metadados:
        # recuperar a etapa sem apagar nem regravar o CSV verificado.
        if not meta.exists():
            with tempfile.NamedTemporaryFile(
                mode="w", prefix=".historico-meta-", dir=pasta,
                encoding="utf-8", delete=False,
            ) as stream:
                temp_meta = Path(stream.name)
                json.dump(info, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp_meta, meta)
            except FileExistsError:
                pass
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)
        if temp_meta is not None:
            temp_meta.unlink(missing_ok=True)
    if destino.is_symlink() or sha256(destino.read_bytes()).hexdigest() != info["sha256"]:
        raise ErroHistoricoDocumental("Evidência final não passou na verificação.")
    _verificar_manifesto_arquivado(meta, info)
    return {**info, "copia": str(destino), "ja_arquivado": ja_arquivado}
