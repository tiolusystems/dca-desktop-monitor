"""Guard de geração documental em torno da rede, fila Tk e exportação.

Verificação completa com SHA/SQLite sempre no worker. No callback Tk apenas
SHA de dois JSONs pequenos e fingerprints de CSV/SQLite, sem reprocessar 13k
linhas nem abrir o banco em thread gráfica.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path

from backend.historical_activation import carregar_historico_ativo


class HistoricoMudouDuranteConsulta(ValueError):
    pass


def _componentes(data_dir, fonte):
    pasta = Path(data_dir).expanduser().resolve() / "evidencias"
    doc = Path(fonte).expanduser().resolve()
    if doc.parent != pasta or not doc.name.startswith("historico-") or doc.suffix != ".csv":
        raise HistoricoMudouDuranteConsulta("Fonte ativa fora da pasta documental.")
    digest = doc.stem.removeprefix("historico-")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise HistoricoMudouDuranteConsulta("Identificador SHA inválido.")
    return (
        (pasta / "historico-ativo.json", True),
        (pasta / f"historico-{digest}.json", True),
        (doc, False),
        (pasta / f"livro-{digest}.sqlite3", False),
    )


def _identidade_rapida(arquivos):
    marcas=[]
    for path, pequeno in arquivos:
        if path.is_symlink():
            raise HistoricoMudouDuranteConsulta("Atalho simbólico documental inesperado.")
        stat = path.stat()
        if not path.is_file():
            raise HistoricoMudouDuranteConsulta("Componente documental ausente.")
        # On NTFS and ext4 even a same-size edit changes ctime_ns; the
        # trusted worker additionally validates the FULL bytes/source & SQLite.
        timestamp=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        digest=sha256(path.read_bytes()).hexdigest() if pequeno else None
        marcas.append((path.name,timestamp,digest))
    return tuple(marcas)


def abrir_snapshot_documental(data_dir, fonte):
    atual=carregar_historico_ativo(data_dir)  # expensive; worker only
    if atual is None or atual.resolve() != Path(fonte).resolve():
        raise HistoricoMudouDuranteConsulta("Fonte de histórico ativo foi trocada.")
    arquivos=_componentes(data_dir,fonte)
    return {"fonte": str(Path(fonte).resolve()),"marcas":_identidade_rapida(arquivos)}


def revalidar_snapshot_rapido(data_dir, snapshot):
    """Fast fail-closed publishing gate; may be called on Tk thread."""
    try:
        atual=_identidade_rapida(_componentes(data_dir,snapshot["fonte"]))
    except (OSError,KeyError,ValueError,TypeError) as exc:
        raise HistoricoMudouDuranteConsulta("Documento mudou ou está inacessível.") from exc
    if atual != snapshot["marcas"]:
        raise HistoricoMudouDuranteConsulta(
            "Arquivos históricos mudaram durante a consulta; valores bloqueados."
        )
    return True
