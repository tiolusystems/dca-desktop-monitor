# DATA-01 — Persistência transacional e migração conservadora

Escopo: substituir gravações diretas no CSV por SQLite sem alterar interface, cálculos financeiros ou os arquivos originais.

## Invariantes
- Arquivo CSV legado **não é alterado, substituído nem excluído**.
- Primeira execução com CSV existente na pasta do aplicativo: ler todos os registros, validar estrutura, dados, datas e números, criar backup byte a byte com SHA-256 e migrar em uma transação.
- Linhas inválidas, extras e valores não finitos bloqueiam **toda** a importação; o sistema jamais omite registros incorretos silenciosamente.
- Reiniciar com CSV idêntico não duplica; se o CSV mudar depois da importação, a operação é bloqueada para exigir conciliação, evitando perder operações efetuadas em uma instalação antiga ainda ativa.
- Se o banco já contiver registros, proibir importação de um segundo CSV sem conciliação/manual; não misturar origens automaticamente.
- Dados novos residem em %LOCALAPPDATA%/DCA Desktop Monitor/portfolio.sqlite3 (Windows) ou diretório XDG correspondente (Linux); arquivos de instalação não contêm dados pessoais.
- Uso de transações SQLite com journaling WAL e synchronous=FULL; falhas nas gravações provocam rollback.
- API legada DataManager preserva as assinaturas usadas pela interface. A contabilidade e o motor de preços não são modificados nesta PR.
- Exportação CSV exige caminho novo e não pode sobrescrever o legado.
- O executável demonstrativo Windows contém o marcador DCA-PREVIEW-MODE e grava somente em preview-data/ ao lado do executável; nunca toca na base do usuário.
- Importação manual de arquivo de outro local existe apenas na camada de serviço; o assistente visual de migração e os atualizadores ficam para PR específica.
- Não constitui versionamento/auditoria imutável das alterações financeiras; isso requer camada posterior.

## Validação
- `python -m unittest discover -s tests -v` em Linux e Windows.
- Confirmar importação sem alteração de bytes, backup com hash, zero duplicação, migração integral/cancelada, compatibilidade do CRUD e persistência após reabertura.
- Windows Preview é necessária para homologação de interface: build bem-sucedido não equivale a execução GUI aprovada.
- Nenhum merge ou release sem aprovação explícita.
