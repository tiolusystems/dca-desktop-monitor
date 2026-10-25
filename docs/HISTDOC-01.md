# HISTDOC-01 — Base documental íntegra antes da conciliação financeira

## Problema

O CSV legado `Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL,Taxa_Corretagem_USDT` só representa uma fração do histórico real. Não representa, sem falsificar conceitos, (a) transferência de BTC entre custodiantes; (b) compra/venda efetiva em BRL ou USDC; (c) taxas descontadas em BTC/BNB/ETH etc.; (d) rendimentos do Simple Earn e transferências internas; (e) posição de custo desconhecido. Importar um CSV reconstruído diretamente no `portfolio.sqlite3` existente é proibido pelo migrador de uso único e poderia duplicar patrimônio.

## Entregue neste PR: etapa de evidências, não lançamento automático

O novo comando **Aplicativo e manutenção → Histórico documental → Conferir e arquivar CSV documental**:

1. Seleciona arquivo na thread da GUI, valida em segundo plano o novo formato documental (26 colunas).
2. Verifica cabeçalho, datas, identificadores determinísticos, SHA declarado da fonte, quantidades finitas, moeda de corretagem e classificação de impacto.
3. Mostra contagem por fonte e SHA-256 da cópia a ser arquivada.
4. Somente com confirmação explícita, copia os bytes para `<diretório de dados>/evidencias/historico-<SHA256>.csv`, cria manifesto JSON e verifica integridade.
5. Não escreve, reinterpreta, exclui nem substitui operações do `portfolio.sqlite3`. Não recalcula saldos, patrimônio, lucro ou custo fiscal. Não publica CSV do usuário no repositório.

Se a origem for alterada entre prévia e arquivamento, recusa. Fontes e tipos diversos continuam separados. Cada execução Spot é marcada `NAO_SOMAR_DUPLICA_LANCAMENTO_BINANCE`, pois suas pernas financeiras já aparecem no histórico de transações Binance. Mercado Pago continua identificado como transcrição particular, nunca como extrato oficial. Custos e corretagens ausentes permanecem ausentes; PTAX de USD não se converte em câmbio executado de USDT.

**O CSV documental não é aceito pelo importador legado e não deve ser renomeado para `meu_diario_operacoes.csv`.**

## Próxima etapa necessária antes de efetivamente alimentar gráficos/cálculos

Implementar, em uma PR independente após testes sintéticos:

- Livro de eventos financeiros multiativo, com quantidade, custódia, moeda de cotação e corretagem na própria moeda; transferências sem resultado realizado.
- Reconstrução de custo BRL e USDT somente a partir de evidência efetiva, admitindo custo explicitamente desconhecido e recusando `0` como substituto.
- Motor de reconciliação por IDs/ordens/custódia, identificação de lançamentos duplicados, saldos de Earn e comparação com snapshot anterior.
- Migração transacional com backup SQLite recuperado em teste, prévia antes/depois, evidências vinculadas a cada lançamento e rollback de uma operação incompleta.
- Homologação Windows/Linux com massas reais em **ambiente isolado**, nunca sobre a única carteira operacional.

**Status:** HISTDOC-01 contém apenas arquivamento, validação e prévia. Não representa reconstrução concluída nem autoriza exclusão/reinstalação do DCA.

## Testes

`python -m unittest tests.test_historical_evidence -v`

O conjunto cobre cópia íntegra, idempotência, não alteração do banco existente, taxa nativa, custo desconhecido, transferência MP, PTAX apenas referencial, duplicação Spot e rejeição de arquivo alterado.
