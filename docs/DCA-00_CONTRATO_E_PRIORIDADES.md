# DCA-00 — Contrato funcional, prioridades e evolução segura

**Situação:** proposta para homologação de negócio.  
**Base observada:** `main` em `62386aab7b4d2842b9bf6c247a347c7478beaca5` (18/10/2026).  
**Decisor:** titular do projeto; implementação posterior por PRs pequenas.  
**Regra de execução:** um problema → uma correção → uma validação → STOP.

## 1. Propósito e princípios obrigatórios

O DCA Desktop Monitor é um aplicativo **desktop, local-first, sem negociação automática** que deve responder:

1. Quanto capital externo efetivamente entrou e saiu da carteira?
2. Quanto foi comprado, vendido e ganho/perdido **por ativo**, inclusive após zerar posições?
3. Qual era o patrimônio e o resultado **em qualquer período**, quando existirem dados históricos válidos?
4. Como instalar, usar, fechar, manter em segundo plano e atualizar voluntariamente **sem perder dados**?

**Invariantes:**
- Nunca apagar nem modificar silenciosamente o CSV original de instalações existentes.
- Nunca usar cotação de hoje para representar custo, resultado ou valor de mercado do passado.
- Se faltarem dados, sinalizar insuficiência de dados; não supor taxa, preço histórico, aporte ou rentabilidade.
- Dados originais são registros auditáveis; resultados, dashboards e agregações são derivados e recalculáveis.
- UX, legibilidade, performance e segurança são requisitos funcionais concomitantes.
- Não adicionar carteira custodial, chaves de negociação, ordens automáticas ou autenticação em nuvem sem aprovação própria.
- `main` estável; PRs em rascunho, testes e demonstração Windows antes de homologação; merge e release separados.

## 2. Conceitos financeiros canônicos

| Conceito | Significado | Limites de interpretação |
| --- | --- | --- |
| Entrada/aporte externo | Transferência de valor de fora para dentro da carteira | `USDT compra` do legado pode representar depósito, mas não prova o custo original em BRL. Identificar origem quando necessário. |
| Retirada externa | Transferência de valor para fora da carteira | `USDT venda` é tratada no legado como saque; não necessariamente venda tributável de cripto. |
| Compras históricas por ativo | Soma dos valores das compras executadas até a data de corte, denominados na moeda de referência da operação | É **giro acumulado** de compras, não aporte externo, nem capital ainda aplicado. |
| Vendas históricas por ativo | Soma dos valores das vendas executadas até a data de corte | É giro de vendas, não lucro. |
| Custo da posição aberta | Custo contábil remanescente das unidades detidas | Difere de compras históricas e de valor de mercado. |
| Lucro/prejuízo realizado | Receita líquida da venda menos custo das unidades alienadas e taxas pertinentes, segundo método aprovado | Independe de preço de mercado atual. Persistir/reconstruir a partir das operações originais. |
| Lucro/prejuízo não realizado | Valor de mercado da posição aberta menos custo da posição | Só disponível com cotação válida da **data de avaliação**. |
| Patrimônio na data | Posições na data × cotações históricas correspondentes + caixa na data | Se faltar cotação válida de qualquer posição material, **não exibir total completo como se exato**. |
| Rentabilidade de operação | Resultado em relação à base de custo apropriada | Definir base para compras parciais, taxas, períodos e recompras. |
| Rentabilidade consolidada | Métrica aprovada com entradas/saídas e períodos explícitos | `P/L total ÷ compras históricas` NÃO deve ser rotulada como rentabilidade efetiva do capital. |

**Custo médio:** por enquanto, método do preço médio móvel usado pelo legado; propor alterações contábeis somente em ADR separada. Compras anteriores ao início do período informam o custo de vendas ocorridas dentro dele. Posições encerradas permanecem na análise histórica, mesmo em empate. Recompras iniciam novo custo aberto, sem apagar resultados anteriores.

**Taxas:** `Taxa_BRL` do CSV é **cotação USDT/BRL**, não taxa de corretagem. O README promete 0,1% de comissão, mas essa promessa não comprova débito efetivo; não inventar cobrança retroativa. Modelar valor bruto/líquido, taxa, moeda e origem somente após levantamento compatível com operações existentes.

**Moedas:** cada valor deve trazer unidade inequívoca (BTC, USDT, BRL etc). Conversão atual para apresentação em BRL não é conversão histórica; conversões históricas exigem taxa fixada por data e fonte.

## 3. Política de dados históricos

- **Operações:** data/hora, identificador imutável, ordem estável, ativo, tipo, quantidade, valor executado, moeda, taxas e origem; histórico de correções sem destruir versão anterior.
- **Cotações:** ativo/par, preço, instante efetivo, granularidade (fechamento diário, intradiário etc.), fonte e instante de captura; persistidas no SQLite com regra de atualização/versionamento e proveniência.
- **Data de avaliação:** aplicar operações ocorridas **até o instante final escolhido**, e cotação daquele dia/instante definida pela política; padronizar fuso e fechamento, registrando convenções.
- **Sem histórico de preço:** permitir calcular o realizado derivado das operações; deixar patrimônio, P/L não realizado e rentabilidade marcada a mercado como **indisponíveis**, não zero.
- **Busca histórica externa:** permitida apenas como etapa explícita de preenchimento da base, armazenando a cotação com sua procedência antes do cálculo. A consulta jamais usará preço contemporâneo como substituto do histórico.
- **Recálculo:** assegurar determinismo ao usar a mesma versão de regras, mesmos registros e mesma base temporal; expor fontes e intervalos incompletos.
- **Período:** separar valores **no intervalo** de acumulados **até a data final**, evitando somas e percentuais enganadores. P/L realizado no intervalo usa custo de compras anteriores, se houver.

## 4. Diagnóstico da versão legada — pendências obrigatórias

| ID | Problema comprovado ou risco identificável | Critério de encerramento |
| --- | --- | --- |
| DATA-01 | CSV é regravado sem escrita atômica, erros podem ser ignorados, sem transações de banco | Persistência SQLite ACID, migração repetível, detecção explícita de linhas problemáticas, backup validado e recuperação. |
| FIN-01 | Posições fechadas podem desaparecer da análise; resultados e percentuais misturam bases | Resultado preservado e indicadores rotulados corretamente, com cenários de empate/perda/lucro/recompra. |
| FIN-02 | Sem cotação o sistema usa zero e pode omitir posição | Ativo continua no patrimônio posicional; avaliação de mercado marcada indisponível quando necessário. |
| FIN-03 | Edição permite combinação incompatível de quantidade/preço/valor | Invariantes centralizadas e teste de rejeição/reconciliação antes da escrita. |
| FIN-04 | USDT e USDC não possuem tratamento financeiro coerente em todas as funções | Tipos de operação e caixa formalizados e testados por moeda. |
| FIN-05 | Comissão de 0,1% anunciada não é demonstrada pelo registro atual | Taxas realmente registradas, sem valores fictícios ou dupla contagem. |
| FIN-06 | Possibilidade de saldos negativos / venda excedente sem validação homogênea | Validação centralizada, regra explícita sobre exceções legadas e nenhuma alteração silenciosa. |
| OPS-01 | Falhas Binance, inicialização bloqueada e threads concorrentes | Aplicação abre offline, cita idade das cotações, sem telas travadas, atualização única e cancelável. |
| QA-01 | Cobertura de testes insuficiente e dependências não fixadas | Testes de regressão executados em PR, dependências rastreadas, erros visíveis. |
| UI-01 | Textos truncados, contraste pobre e distribuição misturada com P/L realizado | Layout responsivo/legível, dois gráficos com conceitos distintos, homologação Windows. |
| DIST-01 | Sem instalador e sem atualizador para usuários do legado | Instalação gerenciada, importação segura, atualização opt-in, rollback/recovery e separação de dados por usuário. |
| DIST-02 | Atalho atual exige executar script e supõe Desktop local | Botão de criação de atalho dentro da aplicação, caminho Windows resolvido corretamente e resultado verificável. |
| OPS-02 | Fechar programa encerra o processo; sem modo bandeja | Modo segundo plano explícito, visível, com restaurar e sair de verdade. |

**Inventário funcional a preservar:** dashboard, registro compra/venda, caixa, histórico/edição, moedas, preços Binance, USD/BRL, interface desktop e controle local do CSV no legado.

## 5. Execução por prioridades / dependências

| Ordem | Prioridade | Entrega isolada | Critério de validação |
| --- | --- | --- | --- |
| DCA-00 | P0 | Este contrato, inventário, matriz de riscos e cenários canônicos | Documento revisado pelo decisor; nenhuma alteração funcional. |
| DATA-01 | P0 | Migração CSV → SQLite, cópia de segurança, idempotência, registros de erro e rollback testado | Dados íntegros em instalação antiga/limpa, importação repetida sem duplicação, CSV original intocado. |
| FIN-01..06 | P0 | Motor financeiro canônico, saldos, taxas, moedas, posições zeradas e edição | Regressões golden-file, reconciliação de P/L, zero omissão de posição. |
| HIST-01 | P1 | Histórico de cotações persistido com tempo/fonte, ausência explícita de dados | Nenhum uso de preço atual ao consultar o passado; reprodutibilidade. |
| ANA-01 | P1 | Análise por ativo e por período; carteira consolidada | Métricas com unidade/base identificada; encerrados visíveis e períodos conciliados. |
| OPS-01 | P1 | Offline, cache com idade, atualização única, tratamento de falhas | Interface abre sem Binance e opera no histórico local. |
| DIST-01 | **P0 para lançamento público** | Instalador, releases, verificador e atualização voluntária | De versões antigas à nova sem perda, confirmação antes de instalar, recuperação em falha. |
| DIST-02 | P1 | Botão **Criar atalho na Área de Trabalho** | Executa aplicativo correto sem terminal, inclusive Desktop redirecionado/OneDrive. |
| OPS-02 | P1 | Modo bandeja/segundo plano | Ocultar/restaurar/sair com consumo limitado e sem processos órfãos. |
| UI-01 | P1 | Revisão visual e acessibilidade | Leitura integral, responsividade, ausência de textos cortados; demonstrativo Windows. |
| REL-01 | P0 para lançamento público | Empacotamento/testes de upgrade/assinatura quando disponível | Release versionada e auditável; manual curto para usuário. |

**Não executar tudo simultaneamente.** Um PR por problema/contrato, revisão, validação Windows com dados fictícios e STOP antes do próximo risco. Reordenar apenas por dependência justificada.

### PRs existentes no início desta decisão

- **PR #1:** preservar histórico de posições fechadas; rascunho, requer revisão da base de rentabilidade e homologação.
- **PR #2:** análise por ativo/período, baseada na branch da #1; rascunho e dependente. Sua existência **não autoriza merge antes da proteção dos dados e da revisão do contrato financeiro**.
- As PRs não substituem a necessidade de contratos e testes de integração sobre SQLite.

## 6. Controles visíveis ao usuário — regras de produto aprovadas para desenvolver

### 6.1 Verificar atualizações / Atualizar se quiser

Local recomendado: **Configurações → Aplicativo → Atualizações**.

- Botão **Verificar atualizações** consulta apenas canal oficial de releases estáveis do fork `tiolusystems/dca-desktop-monitor`.
- Mostrar versão instalada, versão disponível, data, alterações relevantes e procedência. Exibir `Nenhuma atualização disponível` quando não houver publicação; situação offline não é `atualizado`.
- Botão **Atualizar agora**, visível/habilitado somente se houver versão aplicável; pedir confirmação expressa e preservar opção **Agora não**.
- Baixar pacote em local temporário, validar proveniência HTTPS e integridade contra manifesto/hash de release confiável; construir caminho para assinatura de código futura (hash sozinho não autentica o editor).
- Encerrar processo com segurança, fazer cópia de segurança dos dados antes de migrar, executar instalação fora do processo GUI e permitir recuperação se falhar. Nunca sobrescrever SQLite/CSV durante troca do executável.
- Sem baixar/instalar atualização automaticamente sem consentimento. Checagem passiva opcional pode somente **notificar**. Nunca usar branch `main`/PR como feed de atualização.
- Builds de demonstração e previews não devem se apresentar como versões estáveis; diretórios e dados separados do usuário real.
- Se ainda não houver GitHub Releases, informar honestamente. Não mostrar botão funcional fictício.

### 6.2 Criar atalho

Local: **Configurações → Aplicativo → Atalho**; botão claro **Criar atalho na Área de Trabalho**.

- Deve usar caminho do **executável instalado** em distribuição Windows. Modo de desenvolvimento Python é distinto e não pode ser confundido com instalação.
- Resolver a pasta Desktop do usuário pelo mecanismo Windows, inclusive OneDrive/redirecionamento, não assumir `Path.home()/Desktop`.
- Atalho `.lnk` com nome/ícone/working directory corretos; idempotente, sem atalhos duplicados; mensagens de sucesso/erro verificáveis.
- Se já houver atalho para a aplicação, oferecer indicação **Atalho já existe** ou recriação intencional; nunca apontar para preview expirável.
- Não criar atalho automaticamente sem decisão do usuário, salvo opção claramente escolhida no instalador.

### 6.3 Funcionamento em segundo plano

Local: **Configurações → Aplicativo → Segundo plano**.

- Opção explícita **Ao fechar a janela: minimizar para a bandeja**. Padrão de migração: **desativado**, até que o usuário habilite (preserva comportamento conhecido).
- Minimizar para bandeja conserva aplicativo aberto e monitor de preços em memória; **não é serviço Windows nem negociação automática**.
- Ícone na área de notificação com **Abrir** / **Atualizar cotações** / **Sair completamente**; duplo clique restaura.
- Exibir aviso na primeira minimização, indicando onde restaurar e como encerrar, com opção de não mostrar novamente.
- Ao selecionar **Sair completamente**, interromper ciclos de cotação, encerrar threads/ícone e fechar arquivos sem corromper dados.
- Offline, conexões interrompidas e atualizações em segundo plano não podem provocar notificações repetitivas ou uso excessivo de CPU/rede. Intervalo configurável e limites de requisições.
- **Iniciar com o Windows** é opção diferente e fica **desativada por padrão**, caso seja desenvolvida futuramente. Nunca ativar por consequência da criação de atalho.

## 7. Matriz mínima de aceitação antes de publicar aos usuários

1. CSV com operações normais: importação íntegra, conferência de quantidade, valores, datas e hash do original.
2. CSV com linha inválida/duplicada: erro explícito, nenhuma perda nem regravação do original.
3. Migração repetida / cancelada / falha durante gravação: zero duplicação, banco recuperável.
4. Compra → venda total com lucro, prejuízo ou empate: resultado histórico preservado.
5. Venda parcial → recompra → venda total: custo médio e resultados reconciliados.
6. Operação anterior ao período e venda dentro dele: custo histórico correto.
7. Dia histórico sem cotação: valor histórico de mercado indisponível, nunca preço atual ou zero fictício.
8. Desconexão da Binance na abertura e durante atualização: operações locais continuam acessíveis.
9. Conferência de taxas em USDT, BRL ou cripto e de USDT/USDC, sem misturar câmbio e comissão.
10. Nova instalação Windows / atualização de versão anterior / cancelamento / falha: histórico intacto e configuração mantida.
11. Verificar atualização com release nova, ausência de release, internet indisponível e manifesto inválido.
12. Criar atalho em Desktop convencional e redirecionado; clicar abre o **app instalado**, não preview.
13. Fechar para bandeja, restaurar, sair por menu, desligar/reiniciar, segunda tentativa de abertura.
14. Teste visual em Windows: fontes, telas estreitas, escalonamento DPI, modo claro/escuro se suportado, sem textos truncados.

## 8. Portões de governança

- **Design**: regra de negócio e critérios aceitos pelo decisor antes de implementação.
- **Code**: branch isolada; revisões e testes proporcionais ao risco.
- **Windows preview**: executável de homologação com dados fictícios; logs, sem acesso a dados pessoais existentes.
- **Merge**: somente após aprovação explícita.
- **Release**: decisão independente de merge; installer/versionamento/recuperação comprovados.
- **STOP**: nenhuma alegação de teste, build, release ou atualização executada sem evidência verificável.

**Estado deste documento:** planejamento versionado, não comprovação de implementação dos botões nem de migração do banco.
