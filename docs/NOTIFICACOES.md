# Notificações de mensagens recebidas

O item **Caixa de entrada** na navegação mostra o contador de mensagens não lidas de WhatsApp, Instagram, e-mail e SMS recebidas pelas integrações configuradas. Não há um item separado de notificações na sidebar. Dentro da Caixa de entrada, o botão **Não lidas** abre a central e cada item leva à conversa correspondente. Novas mensagens também geram um aviso flutuante no canto superior direito. A leitura pertence ao usuário e à conta atual; outro integrante mantém seu próprio contador.

Mensagens carregadas em uma conversa visível são marcadas como lidas. Também é possível marcar uma conversa ou todas as notificações pela central. Mensagens enviadas, ecos do próprio aplicativo, eventos repetidos e importações de histórico não geram novos avisos. O primeiro carregamento mostra pendências sem disparar alertas antigos.

## Avisos do navegador

Em **Configurações → Notificações**, escolha **Ativar avisos** e conceda a permissão solicitada pelo navegador. Para interrompê-los, use **Desativar avisos** na mesma página. A preferência é específica por navegador, usuário e conta. Os avisos aparecem quando o Antares está em uma aba sem foco, enquanto a aplicação permanece aberta. Não há serviço de push para o navegador fechado. A disponibilidade depende do navegador; os avisos internos funcionam sem essa permissão. Os controles de ativação ficam apenas em Configurações.

O aviso do navegador mostra o remetente e o canal, sem o conteúdo da mensagem. Ao clicar, ele abre a conversa. Abas do mesmo navegador coordenam os alertas por Web Locks e um registro local de identificadores, evitando repetição. Sem Web Locks, a coordenação usa armazenamento local em melhor esforço.

## Operação

- Migração: `20261022_message_notifications`, após `20261022_campaign_channels`. Cria notificações e marcadores de leitura, sem converter o histórico antigo em novas pendências.
- Eventos são gravados na mesma transação da mensagem recebida e isolados por `workspace_id`.
- Consulta autenticada a cada 5 segundos; após falha temporária, tenta novamente em 15 segundos. O navegador pode reduzir a frequência de abas em segundo plano.
- A central mostra as 20 conversas com mensagens não lidas mais recentes; o contador inclui todas as pendências.
- `GET /api/v1/inbox/notifications`, `POST /api/v1/inbox/notifications/read` e `POST /api/v1/inbox/notifications/read-all` exigem sessão e acesso ativo à conta.
- A marcação de leitura usa o identificador da última mensagem carregada e cursores monotônicos por usuário. Mensagens que chegam depois não são marcadas por uma solicitação anterior.

Validação: `scripts/check.sh`, `scripts/verify-postgres.py`, `scripts/verify-migrations.py` e os testes de navegador em `frontend/browser-tests/navigation.test.mjs`. Estes simulam recebimento e a API de notificações do navegador, sem enviar mensagens ou solicitar permissões reais ao computador.
