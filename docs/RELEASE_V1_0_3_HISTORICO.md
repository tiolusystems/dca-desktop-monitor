# DCA Monitor 1.0.3 — monitor histórico documental

## Alteração visível

Na barra principal do DCA, o botão **Histórico documentado (NOVO)** abre
a visualização de **quantidades reconstruídas por ativo/custódia**, com
cotações atuais da Binance (somente quando confirmadas e válidas).

O monitor aceita o CSV documental consolidado de 13.218 registros, preserva
e evidencia os 26 registros antigos sem duplicá-los, distingue o histórico
Binance Spot de Mercado Pago e expõe transações BRL **brutas** documentadas.
Taxas pagas em BTC, BNB, etc. são descontadas na própria moeda.

Se um saldo de custódia é negativo, a avaliação daquele ativo é bloqueada.
Preços ausentes não viram zero nem dados estimados. USDC não é assumido
igual a USDT. A PTAX em USD nunca passa por taxa de operação USDT efetiva.
Custos e lucros históricos incompletos continuam indisponíveis.

**Atenção: não substitui ainda a carteira operacional nem os indicadores
financeiros do dashboard principal**. Continua sendo visão documental de
conferência, não saldo final atestado por corretoras.

## Uso prático no Windows

1. **Não excluir nem reinstalar a versão anterior para apagar dados**.
2. Após a publicação oficial, abrir **Aplicativo / Configurações →
   Verificar atualizações** e utilizar a atualização assistida com backup,
   ou instalar manualmente o pacote oficial da Release.
3. Clicar **Histórico documentado (NOVO)**. Se o histórico já foi arquivado
   pelo aplicativo, é carregado automaticamente; caso contrário, escolher
   `DCA_HISTORICO_DOCUMENTAL_INTEGRAL_2021_2026.csv`.
4. Valores permitidos aparecem; pendências mostram **CONCILIAR**. O botão
   exporta somente relatório de análise, não um novo `meu_diario_operacoes.csv`.

## Publicação

Gate administrativo do workflow `.github/workflows/release-packages.yml`
continua obrigatório. A versão não deve aparecer como download estável sem
aprovação de SHA exato em `DCA_DISTRIBUTION_APPROVED_SHA`, pacote Windows e
Linux, respectivos hashes e confirmação da Release. **Merge ≠ publicação.**

## Limite de garantia

Existem 7 ativos com saldo negativo final na custódia inferida Earn (AXS,
BUSD, COS, DOGE, NEAR, SHIB, UNI). Não há base documental para criar
transações de compensação. Essas posições não são dadas como conciliadas.
O release não deve afirmar que o lucro BRL ou a contabilidade fiscal
histórica da carteira está completa.
