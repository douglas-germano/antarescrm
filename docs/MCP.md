# MCP do Antares

Servidor MCP remoto para que Claude, ChatGPT, Cursor e outros agentes leiam e respondam mensagens, publiquem
no Instagram, respondam comentários e leiam métricas de uma conta do Antares.

- Endereço: `https://antares.douglasgermano.com/mcp`
- Transporte: Streamable HTTP, sem sessão, respostas JSON (`POST` com JSON-RPC 2.0). `GET`/`DELETE` → 405.
- Protocolo: `2025-06-18` (aceita também `2025-03-26` e `2024-11-05`).
- Autenticação: `Authorization: Bearer antares_…`. Tokens são criados em Configurações → Acesso para IAs.

## Tokens

Criados por proprietários e administradores, valem para uma conta e agem em nome de quem os criou; se essa
pessoa perder o acesso à conta, o token para de funcionar. O segredo aparece uma única vez; o banco guarda só
o SHA-256 (`api_tokens`). Validade de 30, 90, 180 ou 365 dias, revogação imediata, último uso registrado.

| Permissão | Ferramentas |
| --- | --- |
| `messages:read` | `list_conversations`, `read_conversation` |
| `messages:send` | `send_message` |
| `instagram:read` | `list_instagram_accounts`, `get_instagram_insights`, `list_instagram_posts`, `list_instagram_comments` |
| `instagram:drafts` | `create_instagram_post` somente com `action: "draft"` |
| `instagram:publish` | `create_instagram_post` com `schedule` ou `publish` (só proprietários e administradores) |
| `instagram:comments` | `reply_instagram_comment` |

`get_account` está sempre disponível. `tools/list` mostra apenas as ferramentas que o token pode usar.

## Ações irreversíveis

`send_message`, `create_instagram_post` (agendar/publicar) e `reply_instagram_comment` exigem `confirm: true`,
são marcadas com `destructiveHint` para o cliente pedir aprovação e ficam no `audit_logs` (`mcp.action.*`,
recurso `api_tokens`) antes de executar. Limite de 60 ações por hora por token. `send_message` aceita
`idempotency_key`: repetir a chamada com a mesma chave não envia de novo.

As regras dos canais continuam valendo: janela de 24 horas e 1.000 caracteres no Instagram, conversas fechadas
não recebem envio, e-mail e SMS entram na fila do worker. Publicações por MCP usam links HTTPS públicos (JPEG
para imagens); o envio de arquivos continua pela tela. Comentários são lidos ao vivo do Instagram (10
publicações recentes ou uma específica) e cada comentário recebe no máximo uma resposta pública e uma privada.

## Configurar um cliente

Claude Code:

```bash
claude mcp add --transport http antares https://antares.douglasgermano.com/mcp --header "Authorization: Bearer antares_..."
```

Clientes com arquivo JSON (Claude Desktop via conector remoto, Cursor e similares):

```json
{"mcpServers": {"antares": {"type": "http", "url": "https://antares.douglasgermano.com/mcp",
  "headers": {"Authorization": "Bearer antares_..."}}}}
```

Conectores web que exigem OAuth (ChatGPT e Claude.ai) ainda não são suportados; o próximo passo é OAuth 2.1
sobre os mesmos tokens e permissões.
