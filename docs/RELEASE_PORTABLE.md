# DCA Monitor — uso no Windows e Linux

Baixe somente em https://github.com/tiolusystems/dca-desktop-monitor/releases
Escolha o ZIP Windows x64 ou o TAR.GZ Linux x64. Extraia a pasta inteira em
um local permanente. Não é necessário instalar Python.

## Windows

Abra DCA-Monitor.exe. Na primeira abertura, o programa tenta criar o atalho
“Portfolio DCA Monitor” na Área de Trabalho, com o novo ícone. A pasta real da
Área de Trabalho é consultada no Windows, inclusive quando está no OneDrive.
Se não for possível criar, use Aplicativo / Configurações → Criar atalho na
Área de Trabalho. Atalhos de outra instalação são preservados; renomeie-os
antes de criar o novo. Não mova nem apague a pasta para a qual o atalho aponta.

Para continuar em segundo plano, ative “Ao fechar a janela, minimizar para
a bandeja” nas configurações. O X ocultará a janela; as cotações continuarão
atualizando. Pelo ícone próximo ao relógio: Abrir, Atualizar cotações ou
Sair completamente. Essa preferência é opcional e não inicia com o Windows.
Se a bandeja falhar, a janela permanece visível.

## Atualizações no Windows

Aplicativo / Configurações → Verificar atualizações → Baixar atualização →
Instalar atualização e reabrir. Nada é instalado sem a sua confirmação.
O download exige versão superior do canal oficial e SHA-256 correto.
A instalação verifica todos os arquivos do manifesto e recusa caminhos
inseguros, arquivos de carteira e pacotes incompletos. A nova versão fica em
`%LOCALAPPDATA%/Programs/DCA-Monitor/versions`, sem substituir a pasta antiga.
Após o fechamento normal, o auxiliar faz e testa um backup portátil da carteira.
Somente então abre a nova versão e atualiza o atalho após a confirmação da GUI.

Os recibos e backups ficam na subpasta `updates` da pasta de dados. Em caso de
falha, preserve as duas versões, o recibo e o backup. Não existe rollback
automático do banco: nunca abra binário antigo sobre banco migrado; restaure
o backup em pasta separada, conferindo gravações posteriores.

A versão 1.0.0 publicada antes deste recurso exige baixar e abrir esta versão
manualmente uma vez. Ela não ganha um instalador retroativamente.

## Linux

Extraia a pasta inteira e abra DCA-Monitor (`chmod +x DCA-Monitor` se necessário).
As funções de bandeja e instalação assistida acima são específicas do Windows.
Verificar atualizações, baixar, preparar backup recuperável e importar CSV
permanecem disponíveis. Para atualizar: encerre, faça backup e extraia a nova
pasta separadamente; confirme a carteira antes de remover arquivos antigos.

## Dados e segurança

O SQLite e as configurações ficam na pasta de dados independente da pasta do
programa. Nenhum CSV ou banco pessoal acompanha os pacotes oficiais. Os cálculos,
a custódia e a escrituração BRL continuam seguindo as regras financeiras de Bruno.
Faça também uma cópia externa do backup. SHA-256 comprova integridade dos bytes;
não substitui certificado Authenticode. O programa não contorna avisos do Windows.
