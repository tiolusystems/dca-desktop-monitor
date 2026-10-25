# RECOVERY-AUDIT-03 — confronto com o backup REAL do DCA

O arquivo **DCA-Recuperacao.zip** exportado pelo usuário é a fonte autoritativa para
aquilo que o seu DCA possui hoje. Não é correto continuar tratando um CSV antigo
como se fosse necessariamente igual ao banco SQLite ativo.

## Funcionalidade implementada

No menu **Aplicativo e manutenção** foi incluído o comando
**Conferir MEU backup DCA contra o histórico**.

1. O usuário seleciona um pacote `DCA-Recuperacao.zip` e depois o histórico
   documental completo (26 colunas).
2. O backend verifica a estrutura fechada do pacote, integridade SHA-256 de cada
   item, `PRAGMA integrity_check`, schema v10 e UUID da carteira.
3. Lê as operações **do SQLite real** em modo read-only; preserva o CSV original
   do próprio ZIP e sinaliza qualquer divergência entre CSV e operações.
4. Verifica que os eventos `DIARIO_LEGADO` referem-se ao mesmo diário e que
   os movimentos Binance vêm de fonte distinta, sem somar ambas as camadas.
5. Agrega fills `BINANCE_SPOT` por ID de ordem, par e lado, mantendo todas as
   taxas em suas **moedas reais**. Compara ativo, lado, preço, quantidade e
   valor bruto. O limiar de 1% é **apenas para procura de candidatos**;
   nunca autoriza a atualização automática.
6. Destaca negócios executados em USDC/BUSD/BRL — nunca convertendo para USDT
   por paridade inventada —, operações não confirmadas e ordens Binance ausentes.
7. Oferece exportação de um CSV **de auditoria**, sem escrever no SQLite
   operacional, alterar resultados, recalcular custo ou publicar dados no GitHub.

## Evidência auditada do usuário (NÃO armazenada no repositório)

O pacote real recebido passou no teste de integridade e identidade. Contém
26 operações; nenhuma posição inicial, posição externa ou movimentação de
custódia. O histórico oficial Spot tem 181 execuções, agrupadas em 80 ordens:
**24 ordens correspondem a lançamentos do SQLite; 56 ordens não constam dele**.
Duas destas últimas são vendas de BTC em janeiro de 2026. Dos 26 registros
atuais, dois não têm negociação Spot correspondente e duas compras BNB
são efetivamente denominadas em USDC. As 12.972 transações Binance originais
não são lançadas novamente a partir das ordens Spot. Essas contagens refletem
o material fornecido, sem afirmar que todas as pendências de custódia foram
resolvidas.

## Limite de escopo

Esta PR é ferramenta efetiva de **auditoria de backup**, ainda não é migração
financeira. Não substituir `portfolio.sqlite3` por um banco auxiliar.
Próxima alteração: plano de substituição reversível de registros e eventos
gerenciados (Spot, custo real em BRL, taxas nativas, transferências, Earn)
com snapshot original e conciliação de saldo oficial.

## Testes

`python -m unittest discover -s tests -p test_recovery_crosscheck.py -v`

Testa ZIP verificado, UUID, correspondência por ordem, USDC separado, taxa BTC
inalterada, cruzamento de outro diário recusado, pacote adulterado recusado,
e ausência de alteração do SQLite.
