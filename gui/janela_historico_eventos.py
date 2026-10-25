"""Janela de consulta do livro documental; nunca permite editar lançamentos."""
from __future__ import annotations

import customtkinter as ctk

from backend.historical_browser import FONTES, consultar_eventos_historicos
from backend.ui_dispatch import UiDispatcher
from config.tema_cripto import (
    BG_CARD, BG_DEEP, BG_INPUT, CYAN, NEON_RED,
    TEXT_PRIMARY, TEXT_SECONDARY,
)


class JanelaConsultaHistorica(ctk.CTkToplevel):
    def __init__(self, parent, diretorio_dados):
        super().__init__(parent)
        self._dados = diretorio_dados
        self._tasks = UiDispatcher(self)
        self._pagina = 1
        self._paginas = 0
        self._busy = False
        self.title("DCA — eventos documentais originais (somente leitura)")
        self.geometry("1100x710")
        self.minsize(850, 520)
        self.transient(parent)
        self.configure(fg_color=BG_DEEP)

        ctk.CTkLabel(
            self, text="LANÇAMENTOS HISTÓRICOS · EVIDÊNCIA, NÃO OPERAÇÕES NOVAS",
            text_color=CYAN, font=ctk.CTkFont("Segoe UI", 16, "bold"),
        ).pack(fill="x", padx=15, pady=(12, 5))

        filtros = ctk.CTkFrame(self, fg_color=BG_CARD)
        filtros.pack(fill="x", padx=15, pady=5)
        self.ativo = ctk.CTkEntry(
            filtros, width=105, placeholder_text="Ativo (BTC)",
        )
        self.ativo.pack(side="left", padx=(9, 5), pady=10)
        self.fonte = ctk.CTkOptionMenu(
            filtros, values=["TODAS", *FONTES], width=230,
            fg_color=BG_INPUT, button_color=BG_INPUT,
        )
        self.fonte.set("TODAS")
        self.fonte.pack(side="left", padx=5)
        self.inicio = ctk.CTkEntry(
            filtros, width=128, placeholder_text="Início AAAA-MM-DD",
        )
        self.inicio.pack(side="left", padx=5)
        self.fim = ctk.CTkEntry(
            filtros, width=128, placeholder_text="Fim AAAA-MM-DD",
        )
        self.fim.pack(side="left", padx=5)
        self.btn_buscar = ctk.CTkButton(
            filtros, text="Pesquisar", width=115,
            command=self._reiniciar,
        )
        self.btn_buscar.pack(side="left", padx=8)

        nav = ctk.CTkFrame(self, fg_color=BG_CARD)
        nav.pack(fill="x", padx=15, pady=(3, 6))
        self.btn_anterior = ctk.CTkButton(
            nav, text="← Anterior", width=120,
            command=lambda: self._mudar_pagina(-1),
        )
        self.btn_anterior.pack(side="left", padx=8, pady=8)
        self.btn_proximo = ctk.CTkButton(
            nav, text="Próxima →", width=120,
            command=lambda: self._mudar_pagina(1),
        )
        self.btn_proximo.pack(side="left", padx=5)
        self.status = ctk.CTkLabel(
            nav, text="Aguardando leitura do livro documental...",
            text_color=TEXT_SECONDARY, anchor="w",
        )
        self.status.pack(side="left", padx=12, fill="x", expand=True)

        self.aviso = ctk.CTkLabel(
            self, text=(
                "BINANCE_SPOT é comprovante redundante, NÃO nova compra. "
                "Mercado Pago é transcrição; taxas e custos desconhecidos "
                "não são zero. O livro financeiro operacional permanece intacto."
            ), text_color=TEXT_SECONDARY, anchor="w", wraplength=1030,
        )
        self.aviso.pack(fill="x", padx=19, pady=(0, 6))
        self.texto = ctk.CTkTextbox(
            self, fg_color=BG_CARD, text_color=TEXT_PRIMARY,
            wrap="none", font=ctk.CTkFont("Consolas", 12),
        )
        self.texto.pack(fill="both", expand=True, padx=15, pady=(0, 14))
        self._escrever("A consulta exibirá até 50 eventos por página, "
                       "com data, fonte, ativo, valor e identificação da origem.")
        self._navegacao()
        self.after(150, self.consultar)

    def _escrever(self, texto):
        self.texto.configure(state="normal")
        self.texto.delete("1.0", "end")
        self.texto.insert("end", texto)
        self.texto.configure(state="disabled")

    def _navegacao(self):
        self.btn_anterior.configure(
            state="disabled" if self._busy or self._pagina <= 1 else "normal",
        )
        self.btn_proximo.configure(
            state="disabled" if self._busy or self._pagina >= self._paginas else "normal",
        )

    def _reiniciar(self):
        if self._busy:
            return
        self._pagina = 1
        self.consultar()

    def _mudar_pagina(self, delta):
        if self._busy:
            return
        nova = self._pagina + delta
        if 1 <= nova <= self._paginas:
            self._pagina = nova
            self.consultar()

    def consultar(self):
        if self._busy:
            return
        filtros = {
            "ativo": self.ativo.get().strip(),
            "fonte": "" if self.fonte.get() == "TODAS" else self.fonte.get(),
            "inicio": self.inicio.get().strip(),
            "fim": self.fim.get().strip(),
            "pagina": self._pagina, "por_pagina": 50,
        }
        self._busy = True
        self.btn_buscar.configure(state="disabled")
        self._navegacao()
        self.status.configure(text="Verificando origem, integridade e eventos...", text_color=CYAN)

        def worker():
            try:
                resultado = consultar_eventos_historicos(self._dados, **filtros)
                erro = None
            except Exception as exc:
                resultado, erro = None, str(exc)

            def done():
                if not self.winfo_exists():
                    return
                self._busy = False
                self.btn_buscar.configure(state="normal")
                if erro is not None:
                    self._paginas = 0
                    self.status.configure(text="Consulta recusada: " + erro,
                                          text_color=NEON_RED)
                    self._escrever("Não é possível consultar eventos sem "
                                   "histórico íntegro.\n" + erro)
                else:
                    self._pagina = resultado["pagina"]
                    self._paginas = resultado["paginas"]
                    self.status.configure(
                        text=f"{resultado['total']} eventos encontrados · "
                             f"página {self._pagina} de {self._paginas} · somente leitura",
                        text_color=CYAN,
                    )
                    self._mostrar(resultado)
                self._navegacao()
            self._tasks.post(done)
        self._tasks.run(worker)

    def _mostrar(self, resultado):
        linhas = [
            "Origem SHA-256: " + resultado["sha256"],
            "Filtro: " + str(resultado["filtros"]),
            "NÃO somar comprovantes Spot ao saldo da conta Binance.",
            "-" * 105,
        ]
        for evento in resultado["eventos"]:
            def campo(chave):
                return str(evento.get(chave) or "—")
            linhas.append(
                f"{campo('data_hora')}  {campo('ativo'):<9} "
                f"{campo('quantidade_assinada'):>18}  "
                f"{campo('fonte')} / {campo('conta')}"
            )
            linhas.append(
                "    " + campo("classe_evidencia") +
                " · " + campo("operacao_origem") +
                " · impacto: " + campo("impacto_saldo")
            )
            if evento.get("valor_brl_documentado") or evento.get("valor_cotacao_executado"):
                linhas.append(
                    "    BRL declarado: " + campo("valor_brl_documentado") +
                    " · execução cotada: " + campo("valor_cotacao_executado")
                )
            if evento.get("taxa_quantidade"):
                linhas.append(
                    "    Taxa documentada: " + campo("taxa_quantidade") +
                    " " + campo("taxa_moeda")
                )
            linhas.append(
                "    Custo: " + campo("custo_aquisicao") +
                " · fonte linha: " + campo("linha_fonte") +
                " · ID: " + campo("id_evento")
            )
            linhas.append("")
        if not resultado["eventos"]:
            linhas.append("Nenhum evento corresponde aos filtros informados.")
        self._escrever("\n".join(linhas))
