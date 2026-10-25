# HIST-09 — Consulta real dos eventos históricos dentro do DCA

## Objetivo

A aba **Histórico integral** já apresenta saldos por ativo e custódia, mas o usuário não conseguia consultar a origem individual dos 13.218 eventos de 2021–2026 sem abrir CSV externo. Esta alteração adiciona o botão **Consultar lançamentos históricos**, que abre uma janela de pesquisa **somente leitura**.

## Funcionalidades

- Consulta paginada (50 eventos por página na interface; limite de API de 200) em ordem cronológica decrescente, sem carregar 13 mil widgets.
- Filtros por ativo, fonte (Binance Transações, Binance Spot, Mercado Pago transcrito, diário legado, câmbio executado ou PTAX de referência) e intervalo de datas civis.
- Exibição da data, ativo, quantidade assinada, custódia, classe, operação de origem, natureza do impacto financeiro, custo conforme declarado, valor bruto comprovado, taxa documentada, ID e linha da fonte.
- Consulta por SQLite documental próprio, em modo read-only com parâmetros SQL, sem gravar ou consultar o banco financeiro `portfolio.sqlite3`.
- Verificação de integridade do histórico ativado antes e depois de cada consulta. Arquivo ou SQLite adulterado bloqueiam a exibição.
- Sem importação duplicada: linhas Binance Spot são evidências de execução, **não** operações adicionais; movimentações Mercado Pago permanecem separadas.
- Operações com custo desconhecido continuam exibindo o texto original de evidência; a consulta não calcula P/L nem inventa taxa/câmbio.

## Uso

1. Atualize para uma versão publicada que inclua HIST-09.
2. Ative o CSV documental completo na aba **Histórico integral** caso ainda não esteja ativo.
3. Clique **Consultar lançamentos históricos**.
4. Filtre `BTC`, `BINANCE_TRANSACOES`, `2021-01-01` etc., e navegue pelas páginas. Nenhum dado operacional é alterado.

## Verificação

`python -m unittest discover -s tests -v` + QA GUI Windows e Linux.

Testes HIST-09: paginação sem duplicação, filtros inclusivos, distinção de Spot, integridade SHA, rejeição de parâmetros inválidos/SQL injection, adulteração do SQLite e do CSV, preservação byte-a-byte do `portfolio.sqlite3`.

**Limitação:** histórico documental não é extrato de saldo certificado. A consulta facilita conciliar lacunas do Earn, mas não elimina os déficits de custódia nem certifica custos BRL ou lucro.
