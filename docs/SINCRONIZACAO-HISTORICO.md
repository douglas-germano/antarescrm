# Sincronização de mensagens antigas

Em **Configurações → Conexões**, os cartões WhatsApp e Instagram permitem iniciar, pausar, retomar e repetir a sincronização. Somente proprietários e administradores da conta podem controlar e consultar essa operação. A fila continua no worker mesmo ao fechar o navegador.

O worker `flask --app run run-worker --no-dispatch` processa os lotes sem habilitar envios. Cada conta tem uma operação por canal. Uma transação PostgreSQL bloqueia a operação por lote e confirma juntas as mensagens e o ponto de retomada. Se o processo cair, o lote é revertido e pode ser refeito. Erros do provedor interrompem a operação e permitem retomada explícita; não há repetição automática ilimitada. Reconectar outro perfil/instância exige uma nova sincronização.

## WhatsApp

A importação geral consulta `chat/findMessages` da instância configurada, em páginas de 200 registros, até uma página vazia. A primeira passagem associa identificadores `@lid` a telefones somente quando a própria chave da mensagem contém a correspondência. A segunda importa as mensagens individuais com conteúdo compatível. Correspondências contraditórias ou ausentes ficam ignoradas e são contabilizadas como registros sem telefone. Grupos e tipos não suportados também são ignorados. Os registros podem ser reavaliados em uma sincronização nova depois que a Evolution receber mais correspondências.

A importação conserva datas, direção e IDs do provedor. Mensagens já existentes não são duplicadas. Mensagens novas que chegam durante a paginação podem deslocar as páginas; repetir a sincronização permite reconciliar o histórico disponível. O botão antigo dentro de uma conversa permanece uma importação rápida de até 500 mensagens pelo telefone; a importação geral não tem esse limite.

A operação lê o que já está no banco da Evolution. Ela não reconecta o aparelho, não altera `syncFullHistory` e não garante buscar no celular mensagens que o provedor não recebeu. Anexos antigos dependem da disponibilidade de download/descriptografia do provedor.

## Instagram

A autorização profissional já vinculada à conta é usada para listar conversas e suas mensagens, percorrendo os cursores das duas listas. Apenas cursores opacos são persistidos; URLs de paginação que possam conter tokens não são armazenadas nem seguidas. Conversas e mensagens continuam limitadas ao que a API da Meta disponibiliza para a autorização atual. Anexos são representados como mensagens de anexo, conforme o tratamento atual da caixa de entrada.

Não há notificações, contadores de não lidas, automações de mensagem recebida ou de contato criado para o conteúdo histórico. As datas originais determinam a ordenação e a janela de resposta existente continua sendo aplicada. Importar uma mensagem antiga não autoriza responder fora da janela permitida.

## API

- `GET /api/v1/history-sync/{whatsapp|instagram}`: estado da operação da conta selecionada.
- `POST /api/v1/history-sync/{whatsapp|instagram}` com `{"action":"start"}`, `{"action":"cancel"}` ou `{"action":"resume"}`.

A resposta apresenta estado, fase, contadores, última atualização e erro sanitizado. Cursores, associação de telefones e credenciais não são retornados ao navegador. Iniciar novamente enquanto já há uma operação ativa devolve a mesma operação. Uma nova execução após conclusão reinicia os contadores e mantém as mensagens já importadas.

A migração `20261028_history_sync` apenas cria a tabela de controle; não inicia nenhuma importação.
