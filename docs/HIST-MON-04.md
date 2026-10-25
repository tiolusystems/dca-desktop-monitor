# HIST-MON-04 — monitor de posições documentais dentro do DCA

O objetivo é permitir que o proprietário **veja o histórico financeiro recuperado
no próprio aplicativo**, sem apagar o banco atual ou mascarar lacunas.

## Uso no aplicativo

**Aplicativo e manutenção → ABRIR MONITOR HISTÓRICO · saldos e cotações atuais**.

Se existir exatamente um CSV arquivado em `<dados>/evidencias/historico-<sha256>.csv`,
o DCA o seleciona automaticamente. Caso contrário, abre o seletor para
`DCA_HISTORICO_DOCUMENTAL_INTEGRAL_2021_2026.csv` (26 colunas).

O monitor:

- Reconstrói saldo assinado Binance Spot, Funding, Alpha, Earn e staking,
  segregando a transcrição Mercado Pago e preservando taxas nas moedas cobradas.
- Nunca duplica as execuções Spot já representadas por pernas financeiras
  no histórico Binance Transações. Não converte USDC para USDT por paridade.
- Busca via Binance (CCXT) a cotação **atual** por ativo e USDT/BRL, em worker
  assíncrono. Usa apenas cotações frescas validadas por `PriceManager`,
  com prazo de até 180 segundos. Falha de rede ou par indisponível => valor
  INDISPONÍVEL, sem valores fabricados.
- Apresenta valores **parciais** em BRL e USDT para ativos com quantidade
  positiva e sem lacuna de custódia. Qualquer negativo final ou histórico
  impede valorizar aquele ativo, mesmo se seu saldo agregado parecer positivo.
- Se **nenhuma** posição não nula puder ser valorizada, não mostra R$ 0:
  subtotal é `None` (indisponível). Sem câmbio corrente, não mostra total BRL.
- Mostra custo de aquisição em BRL e lucro/prejuízo como `None`, jamais zero.
- Exporta um CSV **de visualização**, não um arquivo de compras/vendas para
  reimportação. O arquivo operacional `portfolio.sqlite3` não é alterado.

**Este monitor não substitui ainda os cartões antigos do dashboard nem
certifica o patrimônio final.** O conjunto documental inclui atividades que
precisam ser esclarecidas, como os déficits do Earn. Exibir uma valorização
da posição documental como se fosse **patrimônio oficial completo** seria
um erro financeiro.

## Homologação

`python -m unittest discover -s tests -p 'test_historical_live_monitor.py' -v`

Requer regressão Finance, Windows integrated QA e empacotamento Windows/Linux
antes do merge. Quando possível, conferir com o arquivo particular do usuário
em ambiente isolado; os registros privados não serão colocados no GitHub.
Um release novo exige versão e aprovação conforme
`docs/RELEASE_OPERACAO_TIOLU_V1_0_0.md` — merge não gera instalação por si.

## Próximas mudanças necessárias para o objetivo financeiro integral

1. Comprovar saldos finais por custódia e eliminar, **com evidência**, os
   negativos de Earn; não criar aportes artificiais.
2. Implementar modelo nativo de eventos de várias moedas no SQLite financeiro,
   preservando transferências sem realização de P/L e taxas no ativo.
3. Apurar lotes e custos BRL onde documentalmente comprovados; custos de
   custódia anterior permanecem desconhecidos.
4. Testar migração reversível a partir de backup ZIP original, recalcular
   por data, comparar com saldo efetivo antes/depois e validar em Windows/Linux.
5. Somente então substituir a visão padrão do dashboard financeiro.
