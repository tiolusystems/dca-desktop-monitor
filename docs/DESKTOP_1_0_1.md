# Integração desktop 1.0.1

Base Tiolu: c67fa32e2072aa115c24f3ffe74c4b7270292d18. Referência Bruno/Forja:
1657b8b3fda1d34a06fe2d8cea6184d4d4dfa27f. Nenhum AGENTS.md ou
docs/agent-protocol/ encontrado nas árvores examinadas. CLAUDE.md consultado;
seu texto antigo sobre CSV e ausência de testes não substitui a implementação atual.
Clássica comparada no SHA 4c094f29dee2a51492fffde1f0809521b0748869, principalmente
scripts/update_app.ps1 e o fluxo de atalho/ativação. Não se copiou seu servidor
web, sua política PowerShell nem sua restauração automática de versão sobre SQLite.

## Ícone

Arquivos finais: img/dca-monitor.png e img/dca-monitor.ico. ICO contém resoluções
16, 24, 32, 48, 64, 128 e 256 pixels, geradas do PNG original com transparência.
Criado pela ferramenta integrada image_gen, sem chave API externa.

Prompt: “Use case: logo-brand. Create a finished modern Windows desktop application icon for DCA Monitor, a personal crypto portfolio and recurring investment monitor. Single centered rounded-square dark graphite tile with a distinctive bold geometric D monogram formed from three stepped investment bars and a clean circular portfolio arc, restrained warm orange and ivory accents consistent with finance dashboard. Crisp refined professional software identity, very readable at 16px and 32px, strong simple silhouette, nearly flat vector-like rendering, no text, no currency logos, no bitcoin B, no tiny details, no mockup, no cast shadow, straight-on square composition occupying 88% of canvas. Transparent outer background outside rounded tile. One icon only.”

## Contrato e limites

Atalho inicial automático apenas no Windows empacotado; no ensaio congelado é
suprimido por marcador de carteira sintética. Nenhum atalho alheio é sobrescrito.
Alvo legado DCA só é reconhecido por descrição, ausência de argumentos e identidade
do pacote/versão/hash do executável. O atalho aponta para uma pasta permanente.
Bandeja continua opcional, com callback encaminhado à thread Tk principal.

Instalação assistida: versão superior, URL canônica, tamanho e SHA-256 do ZIP;
novo diretório exclusivo; manifesto de origem e todos os arquivos conferidos;
nenhum arquivo financeiro admitido. Reparse points, links, caminhos externos,
nomes reservados e colisões são recusados. Não há elevação nem política bypass.
O auxiliar aguarda a trava da instância, confere novamente o pacote, exporta backup
e recupera uma cópia temporária, abre a GUI real com a mesma pasta de dados e só
altera o atalho após confirmação com token/PID/versão/executável. Erros preservam
recibos, pastas e backups. Não existe restauração automática sobre dados novos.

A versão 1.0.0 permanece imutável: exige baixar e abrir 1.0.1 manualmente uma vez.
Linux continua com atualização manual; seletor CSV e regressões não são retirados.

## Validação

Testes de unidade cobrem falha de SHA/origem/versão/estrutura, arquivo alterado,
falha de backup, instância aberta, ativação confirmada e candidato que não abre.
O workflow Windows testa GUI/bandeja nativa e ZIP completo. O ensaio
windows_update_smoke.py inicia o auxiliar e o candidato empacotados, verifica
backup/recibo, lê o .lnk por COM e fecha a nova janela normalmente. Helper e
candidato são ambos o build novo; a versão solicitante anterior é modelada.
Isso não comprova instalador retroativo no executável 1.0.0 já publicado.

Publicação depende do CI, integração revisada e SHA definitivo aprovado em
production. O SHA aprovado para 1.0.0 nunca é reutilizado automaticamente.
