# HIST-08 — Reaproveitar a reconciliação histórica sem perder integridade

## Problema

A aba **Histórico integral** carregava e verificava a fonte documental, reconciliava os movimentos Binance/Mercado Pago para descobrir ativos negociáveis e, após consultar as cotações, **reconciliava novamente todo o mesmo CSV** dentro de `calcular_painel_documental`. No histórico real, são 13.218 linhas; a segunda reconciliação repetia validação, ordenação de movimentos, cálculo de custódias e identificação de lacunas Earn, em toda atualização de preço. Além do custo, uma troca do arquivo entre as leituras poderia associar o resumo de uma versão a comprovantes BRL de outra.

## Correção

`calcular_painel_documental` agora aceita `resultado_conciliado` **somente como argumento opcional**. A interface reutiliza a reconciliação feita na mesma execução para escolher os símbolos de mercado, evitando a segunda conciliação integral.

Para não transformar um resultado antigo em patrimônio atual, o motor verifica o SHA-256 do CSV **antes e depois** de percorrer os comprovantes BRL. Se o arquivo não corresponder ao SHA da reconciliação, bloqueia o relatório. A chamada pública sem `resultado_conciliado` mantém o comportamento anterior e os testes existentes.

## Critérios financeiros preservados

- Binance Transações altera quantidades; Binance Spot comprova preços/BRL bruto, não adiciona operações duplicadas.
- Earn/Staking e Mercado Pago permanecem custódias distintas; negativos e lacunas continuam bloqueando valor consolidado.
- Sem evidência de custo, taxa ou câmbio executado, não existe P/L fiscal; os campos continuam `None`.
- Nenhuma alteração em `portfolio.sqlite3`, backup ou saldos.
- A otimização não certifica patrimônio nem substitui extratos oficiais.

## Verificação

`python -m unittest discover -s tests -v`, mais smoke de GUI e pacotes Windows/Linux. Regressões adicionais comprovam reconciliação única, rejeição de fonte modificada antes da cotação e rejeição de arquivo alterado durante a leitura dos valores BRL.
