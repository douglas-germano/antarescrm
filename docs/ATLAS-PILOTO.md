# Atlas

O Atlas escreve uma abertura opcional e responde automaticamente a novas mensagens de texto e de áudio nas conversas cadastradas. O PostgreSQL guarda as conversas selecionadas, a fila, os identificadores da autorização e a sessão OAuth criptografada. O worker do Antares usa o plano ChatGPT autorizado para o workspace e as conexões de WhatsApp e Instagram do CRM.

## Configurar e conectar

1. Aplique a migração `20261105_atlas_db_key`.
2. O Atlas gera uma chave Fernet por workspace ao iniciar a primeira autorização e a guarda no PostgreSQL. O backup completo contém a chave e os tokens criptografados, portanto deve ser protegido como uma credencial. Se uma sessão já usava `ATLAS_ENCRYPTION_KEY`, mantenha a variável até reconectar o ChatGPT uma vez.
3. Exponha a porta do backend em `127.0.0.1` na máquina da instalação. O padrão é `5002`. Se usar outra porta, defina `ATLAS_CALLBACK_PORT`. Use um servidor que omita a query string nos logs de acesso. O Dockerfile do Antares já inclui essa configuração.
4. No navegador da máquina da instalação, abra **Configurações → Conexões → Conectar ChatGPT**. O OAuth local volta a `http://127.0.0.1:<porta>/auth/callback`. Sessões do piloto antigo que dependiam do Keychain precisam de nova autorização.

## Atribuir uma conversa ao Atlas

Na caixa de entrada, abra a conversa de WhatsApp ou Instagram e clique em **Atribuir ao Atlas**. O Atlas responde às próximas mensagens. Para devolver o atendimento ao responsável humano, clique em **Pausar Atlas**.

## Cadastrar pelo terminal

Passe o UUID do workspace, do administrador e da conversa. Use `whatsapp` para uma conversa de WhatsApp ou `instagram` para uma conversa do inbox já iniciada pelo destinatário e com a janela de resposta aberta.

```sh
docker --context colima exec antares-crm-backend-1 flask --app run atlas enroll \
  WORKSPACE_UUID ADMIN_UUID whatsapp CONVERSA_UUID --brief 'Apresente a oficina e pergunte se a pessoa deseja saber mais.' --opening
```

Com `--opening`, o cadastro enfileira uma mensagem inicial. Para responder apenas às próximas mensagens recebidas, omita essa opção. Use `flask --app run atlas status WORKSPACE_UUID ADMIN_UUID` para consultar os resultados e `flask --app run atlas pause WORKSPACE_UUID ADMIN_UUID ATLAS_TARGET_UUID` para cancelar as próximas tarefas daquela conversa.

As mensagens do Atlas aparecem na conversa normal do CRM. Em caso de resultado `unknown`, confira o canal antes de enviar novamente. Uma solicitação leva o objetivo, o texto recebido e até 12 mensagens da mesma conversa ao ChatGPT.

O Atlas transcreve localmente áudios de até 90 segundos e 10 MiB. O ChatGPT recebe a transcrição como parte do contexto da conversa.
