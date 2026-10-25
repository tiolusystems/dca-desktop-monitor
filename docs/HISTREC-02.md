# HISTREC-02 — Reconciliação de saldos documentais por custódia

## Contrato de fonte

O arquivo de 13.218 eventos é documental, não é `meu_diario_operacoes.csv` e não deve entrar no migrador CSV legado. Os 12.972 movimentos de **Binance Transações** já contêm as pernas de compras/vendas e as 178 taxas nativas. As 181 execuções **Binance Spot** são evidência complementar para par, preço, ordem, moeda e corretagem; somá-las novamente duplicaria operações. Nove conversões BRL/USDT são evidências de câmbio executado **naquelas nove operações** e não autorizam aplicar a taxa a compras de outros horários. As 21 linhas Mercado Pago são **transcrição fornecida pelo usuário**, não extrato oficial, e ficam separadas da Binance. O diário legado de 26 lançamentos é comparativo, não fonte adicional de saldo. Nove PTAX são referência USD, jamais câmbio comprovado de USDT.

## Entregas

- `backend/historical_reconciliation.py`: calcula variações reais de quantidade separadas por **Binance:Spot, Binance:Funding, Binance:Alpha, Binance:EARN, Binance:STAKING e MERCADO_PAGO:TRANSCRITO**. Eventos Binance de assinatura de Earn e resgate creditam/debitam espelho Earn; não são vendas/novas compras. Taxas nativas entram **uma única vez** conforme `Transaction Fee`, preservadas em sua própria moeda. Compra/venda Spot em BRL soma valores brutos da negociação como evidência, não como custo médio fiscal. Custos desconhecidos não são preenchidos.
- Apuração reúne variações do mesmo segundo/conta/ativo antes de avaliar mínimos; se algum saldo permanece negativo, sinaliza **ORIGEM_INCOMPLETA_SALDO_NEGATIVO**, sem transação fictícia. Saldos sem negativo ainda são apenas `SALDO_DERIVADO_NAO_CERTIFICADO`, não snapshot oficial do valor em custódia.
- Interface DCA: botão **Conferir saldos históricos e exportar CSV**, usa worker assíncrono; relatório pode ser salvo em outro CSV mas **nunca** mexe no `portfolio.sqlite3`. Não permite sobrescrever o mesmo relatório ou o CSV fonte.
- Testes sintéticos para deduplicação, taxas BTC, mesma data/hora, Earn, origem externa e custo desconhecido.

## Limites e bloqueios de publicação de P/L

A conciliação documental é cálculo independente e **não alimenta ainda os cards do painel financeiro**. Não existe autorização para reinstalar e substituir o SQLite ou migrar saldos sem snapshot atual, comparação, aprovação e testes de recuperação. Alguns saldos negativos também podem resultar de lacunas na origem, movimentações não exportadas ou de modalidades de custódia não espelhadas neste estágio; não servem de indicação para criar compras adicionais. **Não calcule lucro/prejuízo BRL a partir da PTAX para negócios USDT.** Os ganhos de staking/Earn são quantidades; avaliação fiscal depende de documentação adicional.

Passos para fechamento do produto: conciliar eventuais negativos em todas as custódias com saldos finais oficiais; separar transferências internas externas e taxas nas moedas dos extratos; criar snapshots contábeis/versionados para custos documentalmente conhecidos e custos desconhecidos; comparar com o SQLite em uma cópia isolada; homologar mecanismos de migração e reversão em Windows/Linux. A aprovação de merge deste PR valida apenas o relatório documental, não o produto final.

## Manual mínimo

No DCA atualizado: **Aplicativo e manutenção → Conferir saldos históricos e exportar CSV** → selecionar `DCA_HISTORICO_DOCUMENTAL_INTEGRAL_2021_2026.csv` → inspecionar totais e pendências → salvar outro CSV. O antigo importador de operações NÃO deve ser utilizado para o CSV documental nem para o CSV derivado.
