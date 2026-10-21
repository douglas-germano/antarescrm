# Instagram — implantação inicial

## Endereços na Meta
- Callback de eventos: https://antares.douglasgermano.com/api/v1/instagram/webhook
- Retorno OAuth: https://antares.douglasgermano.com/api/v1/instagram/callback
- Configurações no Antares: /configuracoes?tab=conexoes

O GET de webhook exige `hub.mode=subscribe`, compara o token privado `INSTAGRAM_WEBHOOK_VERIFY_TOKEN` e devolve `hub.challenge` em texto puro. O POST preserva os bytes no gateway, não encaminha cookies e valida HMAC-SHA256 (`X-Hub-Signature-256`) no backend antes de persistir eventos. Limite de 2 MB no gateway. Certificado de cliente desativado.

## Configuração privada
No backend/.env: INSTAGRAM_APP_ID (app do Instagram), INSTAGRAM_APP_SECRET, INSTAGRAM_ENCRYPTION_KEY (Fernet), INSTAGRAM_REDIRECT_URI e INSTAGRAM_API_VERSION (v25.0 por padrão). O token inicial fica em INSTAGRAM_ACCESS_TOKEN e só é importado explicitamente pelo comando `flask --app run instagram-import --workspace-id UUID`.

Uma conexão por workspace e um workspace por perfil Instagram. O token inicial do proprietário é vinculado a Advantage Midia. Nenhum cliente herda esse token. Credenciais no banco são cifradas com a chave privada do servidor. Preservar a chave em backup privado junto à configuração; o dump sozinho não permite descriptografar tokens.

## Operação
Configurações → Conexões exibe o perfil e permite OAuth, renovação explícita e desvinculação local. O state de OAuth é aleatório, armazenado como hash, vinculado ao usuário e à conta, tem dez minutos e uso único. O código é trocado somente no servidor por token de longa duração. Revogação definitiva é feita no Instagram; desvincular localmente elimina o token da conexão e interrompe o uso no Antares, preservando o histórico.

Mensagens recebidas criam contato e conversa no canal Instagram da Caixa de entrada. MID é deduplicado por conexão; o timestamp original limita respostas à janela de 24 horas. Contatos são inicialmente identificados pelo ID de remetente da API, sem inferir telefone ou e-mail. Anexos geram indicação textual; visualização e envio de mídia ainda não implementados.

Respostas de texto manuais, até 1.000 caracteres, usam API com idempotência local. O envio é persistido antes da chamada; resultados ambíguos ficam `unknown` e não são reenviados automaticamente. Instagram não participa de disparos em massa nem do outbox genérico.

Inbound executa `received_reply`, interrompe fluxos que param na resposta e emite `message.received` para as regras existentes. Comentários e outros eventos assinados são conservados em instagram_events; não há moderação nem automações específicas de comentários nesta entrega.

## Validação e limites
Testes locais cobrem assinatura, preservação de bytes, deduplicação, isolamento, state expirado e de uso único, credenciais ocultas, janela de resposta e envio sem repetição. Testes externos desta implantação consultam somente o perfil: não enviam DMs nem simulam leads em produção.

Ainda é necessário concluir uma autorização OAuth real no navegador, habilitar a assinatura de mensagens na Meta e provar recebimento e resposta com uma conversa de teste. O sinal verde no painel da Meta confirma configuração, não prova esses fluxos. A chave de aplicativo só será comprovada contra a Meta pela troca OAuth e por um evento real assinado.

Renovação é manual nesta entrega; não há serviço de renovação periódica. Tokens importados sem expires_in têm validade desconhecida exibida como tal. App Review, permissões avançadas e publicação na Meta continuam pendentes para clientes externos. Não submeter análise antes de registrar esses fluxos reais.

## Evidência desta publicação — 21/10/2026
Build `_X7iGgbQ9vlH-eYNFsP0z`. Migração PostgreSQL aplicada com contagens de registros preexistentes e formulários ativos preservados. Backend: 105 testes aprovados e 7 ignorados por requisitos de ambiente. Gateway/Instagram: 16 testes aprovados. Build e tipos aprovados. Perfil confirmado pela API v25.0. API autenticada e gateway público retornaram conexão configurada, sem expor token. Evento vazio assinado retornou 200; requisição sem assinatura retornou 401. Nenhuma DM de teste foi enviada e nenhum lead sintético foi criado em produção.

Tela Conexões conferida com perfil e controles reais; em largura de 390 px, documento mede 390 px, sem overflow horizontal. Captura local: output/playwright/instagram-connections.png. Sessão temporária de inspeção encerrada e arquivo de autenticação removido. OAuth real e conversa real continuam pendentes de ação do titular no Instagram.
