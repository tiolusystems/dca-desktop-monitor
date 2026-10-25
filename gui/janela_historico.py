"""Aba financeira documental: posições desde 2021, sem enganar sobre lucro.

A carteira antiga é preservada. Apenas eventos comprovados entram na
reconstrução; retornos e custos BRL incompletos ficam indisponíveis.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from backend.ui_dispatch import UiDispatcher
from backend.historical_activation import (
    ativar_historico_documental, carregar_historico_ativo,
    ErroAtivacaoHistorica,
)
from backend.historical_evidence import validar_historico_documental
from backend.historical_live_monitor import calcular_painel_documental
from config.tema_cripto import (
    BG_DEEP, BG_CARD, BG_INPUT, BTC_ORANGE, CYAN, NEON_RED,
    TEXT_PRIMARY, TEXT_SECONDARY,
)


class JanelaHistorico(ctk.CTkFrame):
    """Aba 100% independente de registros, posição fiscal e saldo USDT legado."""

    def __init__(self, parent, data_manager):
        super().__init__(parent, fg_color=BG_DEEP)
        self._tasks = UiDispatcher(self)
        self._data_dir = Path(data_manager._store.diretorio)
        self._painel = None
        self._origem = None
        self._busy = False
        self._construir()
        self.after(100, self.recarregar)

    def _construir(self):
        ctk.CTkLabel(
            self, text="CARTEIRA HISTÓRICA DOCUMENTADA · 2021–2026",
            font=ctk.CTkFont("Segoe UI", 19, "bold"),
            text_color=BTC_ORANGE,
        ).pack(fill="x", anchor="w", padx=18, pady=(12, 5))
        self.status = ctk.CTkLabel(
            self, text="Verificando histórico local...",
            text_color=TEXT_SECONDARY, anchor="w", justify="left",
            wraplength=1020,
        )
        self.status.pack(fill="x", padx=19, pady=(2, 5))
        controls = ctk.CTkFrame(self, fg_color=BG_CARD)
        controls.pack(fill="x", padx=16, pady=7)
        self.btn_import = ctk.CTkButton(
            controls, text="Importar e ativar histórico completo (CSV)",
            command=self.escolher_historico, fg_color=BTC_ORANGE,
        )
        self.btn_import.pack(side="left", padx=9, pady=9)
        self.btn_update = ctk.CTkButton(
            controls, text="Atualizar cotações e saldos",
            command=self.recarregar, fg_color=BG_INPUT,
        )
        self.btn_update.pack(side="left", padx=6)
        self.btn_export = ctk.CTkButton(
            controls, text="Exportar relatório", command=self.exportar,
            fg_color=BG_INPUT,
        )
        self.btn_export.pack(side="left", padx=6)
        self.summary = ctk.CTkLabel(
            self, text="Nenhum patrimônio foi modificado.",
            text_color=CYAN, anchor="w", justify="left", wraplength=1020,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
        )
        self.summary.pack(fill="x", padx=19, pady=(5, 5))
        self.notice = ctk.CTkLabel(
            self,
            text=("IMPORTANTE: valores com comprovação e cotação válida são "
                  "subtotais, NÃO o patrimônio consolidado. Custo de aquisição "
                  "e P/L desconhecidos NÃO são zero. O dashboard anterior "
                  "permanece preservado como histórico legado separado."),
            text_color=NEON_RED, anchor="w", justify="left",
            wraplength=1030,
        )
        self.notice.pack(fill="x", padx=19, pady=(2, 9))
        self.table = ctk.CTkTextbox(
            self, wrap="none", fg_color=BG_CARD,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont("Consolas", 12),
        )
        self.table.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self._escrever("Escolha o histórico documental completo (CSV com 26 colunas).\n"
                       "O aplicativo não apaga nem reimporta as 26 operações antigas.\n")

    def _escrever(self, texto):
        self.table.configure(state="normal")
        self.table.delete("1.0", "end")
        self.table.insert("end", texto)
        self.table.configure(state="disabled")

    def _ocupar(self, texto):
        self._busy = True
        self.btn_import.configure(state="disabled")
        self.btn_update.configure(state="disabled")
        self.btn_export.configure(state="disabled")
        self.status.configure(text=texto, text_color=CYAN)

    def _liberar(self):
        self._busy = False
        self.btn_import.configure(state="normal")
        self.btn_update.configure(state="normal")
        self.btn_export.configure(state="normal")

    def escolher_historico(self):
        if self._busy:
            return
        origem = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Selecione o CSV documental INTEGRAL (não o diário legado)",
            filetypes=[("CSV documental", "*.csv")],
        )
        if not origem:
            return
        self._ocupar("Verificando todos os eventos e a origem documental...")
        def validar():
            try:
                info = validar_historico_documental(Path(origem))
                error = None
            except Exception as exc:
                info, error = None, str(exc)
            def concluido():
                if not self.winfo_exists():
                    return
                if error:
                    self._liberar()
                    self.status.configure(text="CSV recusado: "+error,
                                          text_color=NEON_RED)
                    return
                aprovado = messagebox.askyesno(
                    "Ativar histórico verificável",
                    f"Eventos comprovados/documentais: {info['quantidade']}\n"
                    f"Fontes: {', '.join(info['fontes'])}\n"
                    f"SHA-256: {info['sha256']}\n\n"
                    "Criar arquivo e banco históricos próprios?\n"
                    "Seu portfolio.sqlite3 existente NÃO será alterado.\n"
                    "Valores/custos incompletos continuarão não apurados.",
                    parent=self.winfo_toplevel(),
                )
                if not aprovado:
                    self._liberar()
                    self.status.configure(text="Importação cancelada; nenhuma alteração.")
                    return
                self.status.configure(text="Arquivando e validando o histórico...",
                                      text_color=CYAN)
                def ativar():
                    try:
                        importado = ativar_historico_documental(
                            Path(origem), self._data_dir,
                            sha_confirmado=info["sha256"],
                        )
                        err = None
                    except Exception as exc:
                        importado, err = None, str(exc)
                    def finalizar():
                        if not self.winfo_exists():
                            return
                        self._liberar()
                        if err:
                            self.status.configure(text="Ativação recusada: "+err,
                                                  text_color=NEON_RED)
                        else:
                            self.status.configure(
                                text=f"{importado['eventos']} eventos arquivados. "
                                     "Banco antigo preservado. Recalculando...")
                            self.recarregar()
                    self._tasks.post(finalizar)
                self._tasks.run(ativar)
            self._tasks.post(concluido)
        self._tasks.run(validar)

    def recarregar(self):
        """Validate archive, reconcile balances and fetch quotes OFF the Tk thread.

        A 2021–2026 CSV plus PRAGMA integrity_check can take seconds on disk;
        neither operation may freeze the GUI or the Linux CSV file picker.
        """
        if self._busy:
            return
        self._ocupar("Verificando a fonte documental e o banco histórico...")
        def worker():
            origem = None
            report = None
            try:
                origem = carregar_historico_ativo(self._data_dir)
                if origem is not None:
                    from backend.backend import PriceManager
                    from backend.historical_reconciliation import reconciliar_historico_documental
                    from backend.historical_quotes import consultar_cotacoes_historicas
                    bruto = reconciliar_historico_documental(origem)
                    symbols = sorted({
                        row["ativo"] for row in bruto["saldos"]
                        if row["ativo"] not in ("BRL", "USDT")
                        and Decimal(row["saldo_algebrico"]) != 0
                    })
                    prices = PriceManager()
                    cotacoes, cambio, sem_mercado = consultar_cotacoes_historicas(
                        prices, symbols,
                    )
                    report = calcular_painel_documental(
                        origem,
                        cotacoes_usdt=cotacoes,
                        cambio_usdt_brl=cambio,
                        instante_cotacoes=datetime.now(timezone.utc).isoformat(),
                    )
                    report["ativos_sem_mercado_usdt"] = sem_mercado
                erro = None
            except Exception as exc:
                erro = str(exc)

            def done():
                if not self.winfo_exists():
                    return
                self._liberar()
                if erro is not None:
                    # Never leave the previously rendered valuation looking
                    # valid after the source or the documentary DB fails.
                    self._origem = None
                    self._painel = None
                    self.status.configure(
                        text="Histórico indisponível: " + erro,
                        text_color=NEON_RED,
                    )
                    self.summary.configure(
                        text="Nenhum valor histórico pode ser apresentado sem integridade."
                    )
                    self._escrever(
                        "Arquivo documental ou cotações não validados. "
                        "O banco operacional permanece preservado.\\n"
                        + erro
                    )
                    return
                if origem is None:
                    self._origem = None
                    self._painel = None
                    self.status.configure(
                        text="Histórico ainda não ativado. "
                             "Use Importar e ativar histórico completo (CSV).",
                        text_color=TEXT_SECONDARY,
                    )
                    self.summary.configure(
                        text="Nenhum patrimônio histórico foi carregado."
                    )
                    self._escrever(
                        "Selecione o CSV documental integral para iniciar.\\n"
                        "O diário legado não será alterado."
                    )
                    return
                self._origem, self._painel = origem, report
                self._exibir(report)
            self._tasks.post(done)
        self._tasks.run(worker)

    @staticmethod
    def _valor(numero, unidade):
        if numero is None:
            return "INDISPONÍVEL"
        from decimal import Decimal
        bruto = f"{Decimal(numero):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        return unidade + bruto

    def _exibir(self, report):
        gaps = len(report["ativos_com_lacuna_custodia"])
        self.status.configure(
            text=(f"{report['eventos_documentais']} eventos de origem · "
                  f"{report['quantidade_ativos']} ativos · "
                  f"{report['posicoes_custodia']} posições por custodiante · "
                  f"{gaps} ativos com lacunas. "
                  f"{len(report.get('ativos_sem_mercado_usdt', []))} ativos sem mercado USDT. "
                  f"Cotações: {report['instante_cotacoes_utc']}"),
            text_color=CYAN if not gaps else NEON_RED,
        )
        self.summary.configure(
            text=("Subtotal disponível: " +
                  self._valor(report["subtotal_avaliavel_brl"], "R$ ") +
                  "  |  " + self._valor(report["subtotal_avaliavel_usdt"], "USDT ") +
                  ". NÃO inclui ativos sem preço/custódia verificável."),
        )
        lines = [
            f"{'ATIVO':<9} {'QUANTIDADE REAL DOCUMENTADA':>27} "
            f"{'VALOR BRL':>19}  SITUAÇÃO",
            "-" * 110,
        ]
        for row in report["ativos"]:
            qty = row["quantidade_documental"]
            if Decimal(qty) == 0 and not row["pendencias_custodia"]:
                continue
            lines.append(
                f"{row['ativo']:<9} {qty:>27} "
                f"{self._valor(row['valor_brl'],'R$ '):>19}  {row['estado']}"
            )
            for custodia, saldo in sorted(row["custodias"].items()):
                if Decimal(saldo) != 0:
                    lines.append(f"    ↳ {custodia}: {saldo} {row['ativo']}")
            if row["pendencias_custodia"]:
                lines.extend("    ↳ A CONCILIAR: " + note for note in row["pendencias_custodia"])
            brl_binance = Decimal(row["compras_brutas_brl_binance"])
            brl_mp = Decimal(row["compras_brutas_brl_mp_transcricao"])
            if brl_binance:
                lines.append("    Binance: compras SPOT em BRL (valor bruto) "+
                             self._valor(str(brl_binance), "R$ "))
            if brl_mp:
                lines.append("    Mercado Pago: compras BRL transcritas (valor bruto) "+
                             self._valor(str(brl_mp), "R$ "))
        lines.extend([
            "", "Fonte SHA-256: "+report["fonte_sha256"],
            "Resultados BRL e bases fiscais: NÃO APURADOS SEM PROVAS.",
            "Somatório da carteira antiga NÃO foi acrescentado a este histórico.",
        ])
        self._escrever("\n".join(lines))

    def exportar(self):
        if self._busy or self._painel is None:
            return
        destino = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),title="Exportar relatório (NÃO importar no DCA)",
            defaultextension=".csv",
            initialfile="DCA-carteira-documental-NAO-IMPORTAR.csv",
            confirmoverwrite=False,
            filetypes=[("Relatório CSV", "*.csv")],
        )
        if not destino:
            return
        fields = ["ativo", "quantidade_documental", "custodias", "valor_usdt",
                  "valor_brl", "estado", "pendencias_custodia", "lacuna_temporal",
                  "custo_historico_brl", "lucro_prejuizo_brl",
                  "compras_brutas_brl_binance", "vendas_brutas_brl_binance",
                  "compras_brutas_brl_mp_transcricao", "vendas_brutas_brl_mp_transcricao"]
        try:
            with Path(destino).open("x", encoding="utf-8-sig", newline="") as fp:
                writer = csv.DictWriter(fp, fieldnames=fields)
                writer.writeheader()
                for item in self._painel["ativos"]:
                    entry = {key: item[key] for key in fields}
                    for key in ("custodias", "pendencias_custodia"):
                        entry[key] = json.dumps(entry[key], ensure_ascii=False)
                    writer.writerow(entry)
        except Exception as exc:
            messagebox.showerror("Arquivo não exportado", str(exc),
                                 parent=self.winfo_toplevel())
            return
        messagebox.showinfo("Exportação concluída",
                            "Relatório de conferência criado. "
                            "O banco financeiro não foi modificado.",
                            parent=self.winfo_toplevel())
