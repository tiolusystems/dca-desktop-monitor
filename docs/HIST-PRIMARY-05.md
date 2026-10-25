# HIST-PRIMARY-05 — Ativação da carteira histórica no DCA

## Finalidade

Transformar o CSV histórico de 13.218 eventos — Binance Transações (12.972), Binance Spot (181 comprovantes), Mercado Pago transcrito (21), diário original (26) e câmbios/índices (18) — de arquivo auxiliar em **fonte ativa da aba principal de consulta documental**, SEM substituir a base de dados operacional.

## Fluxo no DCA Desktop

1. Abra a aba **📚 Histórico integral**, agora uma aba de primeiro nível da GUI.
2. Clique em **Importar e ativar histórico completo (CSV)** e selecione
   `DCA_HISTORICO_DOCUMENTAL_INTEGRAL_2021_2026.csv`.
3. O DCA valida os 26 campos, IDs, datas, SHA da fonte, corretagens e impacto financeiro. A prévia pede confirmação.
4. Após confirmar, o DCA arquiva uma cópia com SHA inalterável em
   `<dados>/evidencias/historico-<sha>.csv`, materializa o banco
   `livro-<sha>.sqlite3` e somente após ambas as verificações escreve o pequeno
   `historico-ativo.json` de forma atômica.
5. A aba lê automaticamente o histórico selecionado **em todas as próximas inicializações**, comprovando SHA e integridade SQLite. O DCA seleciona essa aba por padrão.
6. Em segundo plano, consulta cotações atuais Binance para as posições com ativo, com preço e câmbio **apenas quando válidos**, e mostra valores parciais, quantidade por ativo, lacunas de custódia e BRL bruto documentado.

**Não é necessário excluir nem reimportar o diário legado; o programa mantém o `portfolio.sqlite3` intacto.**

## Contratos financeiros

- As transações Binance são a fonte exclusiva de movimento da conta Binance. Fills Spot são comprovações de preço e taxa; não viram segunda compra.
- O diário antigo do usuário não se soma novamente.
- Mercado Pago é transcrição; não contém taxas garantidamente zero. Transferência não é venda.
- Earn/Staking permanecem custódias distintas; saldos negativos e lacunas são sinalizados e não compensados com compras fictícias.
- USDC não tem paridade 1:1 presumida. PTAX do dólar não vira cotação executada de USDT/BRL.
- **Custo BRL, P/L realizado/não realizado, ganhos fiscais e patrimônio consolidado continuam não apurados** na ausência de documentação. Subtotais avaliáveis não podem ser denominados total da carteira.
- O dashboard legado continua visível, mas não é misturado à aba documental.

## Conclusão e entrega final pendente

Este módulo resolve a **persistência e leitura efetiva do histórico no aplicativo**, até então dependentes de repetir a seleção manual do CSV, mas NÃO resolve as lacunas e custos antigos nem autoriza declarar “lucro real” no painel geral. Publicação exige versão posterior validada e aprovação SHA exato pelo ambiente `production`. Não usar o banco SQLite documental no lugar do SQLite principal.

## Validação

`python -m unittest discover -s tests -v` e QA de GUI no Windows/Linux.

Cenários adicionais automatizados: validação SHA após importação, recusa de documento/custódia adulterados, idempotência, contagem de fonte, novo livro com custo `NULL`, origem sem cadastro em carteira, e comparação byte-a-byte comprovando ausência de alteração do `portfolio.sqlite3`.
