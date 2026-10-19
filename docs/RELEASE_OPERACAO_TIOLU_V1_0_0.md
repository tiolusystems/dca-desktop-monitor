# DCA Monitor v1.0.0 — publicação controlada no fork Tiolu Systems

## Identidade e escopo

- Repositório de publicação: `tiolusystems/dca-desktop-monitor`.
- Código de origem: `forjasystems-bhm/dca-desktop-monitor`, branch `main`, base `1657b8b3fda1d34a06fe2d8cea6184d4d4dfa27f` (19/10/2026).
- Branch de integração: `release/dca-v1.0.0-forja-official` (no fork existente da Tiolu, sem alterar a `main` da Forja).
- Canal consultado pelo aplicativo: `https://api.github.com/repos/tiolusystems/dca-desktop-monitor/releases/latest`.
- Pacotes finais: `DCA-Monitor-v1.0.0-Windows-x64.zip` e `DCA-Monitor-v1.0.0-Linux-x64.tar.gz`, além das somas SHA-256.
- Não se trata de instalador: são pastas portáteis. A instalação/troca automática de executáveis e rollback automático não fazem parte do escopo v1.0.0.
- A autoria original e licença MIT são preservadas. A publicação no fork não transfere a titularidade do repositório da Forja.

## Verificações necessárias antes de publicar

1. Revisar o diff contra a última `main` da Forja; não sobrescrever correções posteriores. Conferir que a regressão do seletor CSV Linux utiliza o caminho relativo ao pai Tk e relata falhas de callback.
2. Aprovar e integrar por PR em `tiolusystems/main`, com histórico preservado. Não alterar diretamente `forjasystems-bhm/main`.
3. No commit integrado definitivo, exigir CI Windows e Linux: regressão financeira/SQLite, seletor CSV real sob Xvfb, abertura de GUI do executável congelado, saída normal, segunda abertura, recuperação e manifesto completo após extração. Guardar links de execução e SHA exato.
4. Governança F19, configurada por mantenedor no GitHub (não apenas em YAML): regras sobre `main`, tags `v*`, revisão independente, ambiente protegido `production`, inventário e desativação dos antigos caminhos de publicação; testes negativos de bloqueio. Não contornar regras ou usar bypass.
5. Definir no ambiente `production` a variável `DCA_DISTRIBUTION_APPROVED_SHA` igual ao SHA **final** integrado de `main`. A revisão humana deve aprovar exatamente este SHA, não o HEAD anterior da PR.
6. Criar a tag `v1.0.0` sobre aquele mesmo SHA. O workflow `.github/workflows/release-packages.yml` deve produzir **ambos** os pacotes e validar os arquivos SHA-256 antes de publicar uma única Release permanente.
7. Conferir na página `https://github.com/tiolusystems/dca-desktop-monitor/releases` os dois assets, versões, nomes e checksums. Testar `releases/latest` a partir de uma versão inferior, incluindo rejeição de arquivo adulterado, arquitetura incompatível e downgrade.
8. Homologar em computadores Windows e Linux representativos usando somente dados sintéticos e cópia protegida de dados; testar importação CSV, travamento/reentrada do seletor, backup, recuperação e abertura offline. Não utilizar o único arquivo financeiro real.

## Condições de parada (STOP)

- Falha em qualquer job da CI do commit integrado.
- Proteção administrativa F19 não comprovada, ausência de revisor responsável ou variável SHA divergente.
- Releases existentes sob a mesma tag; não sobrescrever um artefato publicado.
- Pacote parcial, assinatura/hash inválido, mistura de builds, dados financeiros acidentalmente empacotados ou falha de recuperação.
- Comportamento da GUI Linux ainda não reproduzido/homologado no ambiente-alvo do Bruno.

## Procedimento para o usuário

**Windows:** baixar o ZIP completo da Release, extrair a pasta inteira e executar `DCA-Monitor.exe`.  
**Linux:** baixar o TAR.GZ completo, extrair e executar `DCA-Monitor` (pode exigir `chmod +x`).  
Não é necessário Python para executar os binários finais. Dados pessoais permanecem fora da pasta substituível do programa. Atualização requer fechar o aplicativo, preparar backup recuperável, extrair a nova pasta e validar os dados antes de atualizar atalhos.

## Evidência

Este documento não é recibo de CI, merge, aprovação, publicação ou homologação. Registrar SHA final, links de CI, aprovação, tag e release após sua ocorrência efetiva.

## Validação do commit integrado

O workflow oficial também executa os jobs de pacotes no push em `main`, sem
publicar nessa execução. A publicação pela tag exige que o SHA aprovado seja
exatamente o HEAD atual de `origin/main`, além da ancestralidade e versão.
`tests/test_release_commit_gate.py` executa o gate real em histórico Git sintético:
aprovação ausente ou divergente, ancestral antigo e referência/versão incorretas
devem ser recusados. Esses testes não comprovam proteções administrativas do GitHub.
