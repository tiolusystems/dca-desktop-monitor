# HIST-12 — Recuperação portátil também protege o histórico ativo

## Falha identificada

A carteira histórica introduzida nas PRs #38–#44 é armazenada em
`<dados>/evidencias/`, **fora** do `portfolio.sqlite3`.
Até HIST-12, `backend/recovery_bundle.py` exportava somente o banco operacional,
CSV legado e configurações. Restaurar apenas esse ZIP em um novo computador
poderia preservar a carteira antiga, mas **perder o histórico ativo de 2021–2026**.

## Correção

- A exportação do pacote portátil agora verifica a fonte histórica ativa e
  acrescenta o CSV documental imutável, o manifesto e o marcador de ativação
  ao mesmo ZIP, com SHA-256 por arquivo.
- O banco `livro-<sha>.sqlite3` é **derivado** e não é duplicado no ZIP:
  a recuperação o reconstrói em uma pasta nova e só aceita o pacote após
  verificar integralmente origem, manifesto, saldo por custódia e integridade.
- Se o histórico ativo estiver adulterado, a exportação é recusada. O programa
  não anuncia falsamente um backup completo.
- Pacotes antigos sem histórico continuam aceitos. Arquivos ZIP com caminhos
  extras, fonte histórica incompleta ou hashes divergentes são recusados.
- O `portfolio.sqlite3` operacional e os backups preexistentes não são
  alterados. Recuperação permanece **somente em diretório novo**, sem ativação
  automática ou sobrescrita de dados.
- Se um backup independente estiver configurado, o ZIP também protegerá o
  histórico ativo; considerar consumo adicional de armazenamento por backup.

## Escopo de garantia

O pacote protege o **histórico ativo**. Evidências arquivadas anteriormente,
mas não ativas, não são exportadas nesta versão. A ausência de documentos
financeiros não é suprida por este procedimento. Custos, rendimentos e P/L
BRL continuam não apurados quando faltarem comprovantes.

## Testes

`python -m unittest discover -s tests -v`

Cenários HIST-12: recuperação em novo diretório, restauração de CSV+manifesto+
ponteiro, reconstrução e integridade do SQLite documental, integridade da
carteira operacional, compatibilidade de pacotes antigos, rejeição de
manipulação do CSV mesmo com SHA do ZIP recalculado, rejeição de manifesto
ausente e falha fechada quando o histórico original estiver corrompido.

A publicação da versão oficial segue sujeita à aprovação administrativa
`DCA_DISTRIBUTION_APPROVED_SHA`, revisão da PR e CI Windows/Linux.
