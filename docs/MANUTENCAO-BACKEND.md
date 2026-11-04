# Manutenção do backend

O backend continua em Flask e SQLAlchemy, organizado como uma aplicação única com módulos por domínio. Esta refatoração preserva os endereços e métodos HTTP existentes e não exige alteração de schema do banco.

## Rotas e operações

As rotas validam autenticação, parâmetros, assinatura de webhook e formato da entrada; os serviços executam as operações de negócio. Uma rota não deve chamar outra função de rota decorada.

- `app/routes/_message_input.py` interpreta JSON e multipart dos dois endpoints de envio de WhatsApp.
- `app/services/messaging.py` compartilha envio, enfileiramento e preparação de lotes.
- `app/services/inbox.py` monta a lista unificada de conversas.
- `app/services/incoming.py` materializa recebimentos e suas notificações na transação do chamador.
- `app/schemas/communications.py` concentra os contratos de entrada dessas operações.

`AccountContext` recebe explicitamente os identificadores da conta e do usuário. A camada HTTP o constrói com `current_account()` somente depois de `@require` validar a sessão e a autorização. Ele não autentica uma pessoa por conta própria: não o construa com um workspace arbitrário recebido do cliente.

As consultas de caixa de entrada e notificações podem ser testadas com um contexto de aplicação e uma conta explícita, sem depender de `flask.g` ou de uma requisição HTTP. O isolamento por `workspace_id` continua obrigatório.

## Instagram

O pacote `app/services/instagram/` mantém a API pública dos serviços anteriores:

| Módulo | Responsabilidade |
| --- | --- |
| `client.py` | HTTP do provedor, OAuth e primitivas de credenciais |
| `connections.py` | Vínculos de contas e assinaturas de webhooks |
| `profiles.py` | Atualização de perfis de contas e contatos |
| `events.py` | Deduplicação e encaminhamento de eventos |
| `messages.py` | Ingestão de mensagens, reconciliação de ecos e payloads |
| `comments.py` | Recebimento e respostas de comentários |
| `outbound.py` | Orquestração dos envios de mensagens |

Chamadas HTTP internas usam o módulo `client` explicitamente. Nos testes, substitua esse adaptador ou os métodos do transporte. O `__init__.py` reexporta as funções consumidas pelas rotas e automações; não acrescente regras de negócio ali.

## Transações de entrega

`delivery_transactions.commit_delivery()` nomeia os dois commits existentes nos envios diretos de WhatsApp/Instagram e no dispatcher de comunicação:

1. `claim`: persiste a intenção de envio antes de chamar o provedor.
2. Chamada ao provedor, fora dessa transação já concluída.
3. `outcome`: persiste a confirmação ou o estado sem confirmação.

Não substitua esses limites por um único commit ao final da requisição. Uma falha de rede pode acontecer depois de o provedor aceitar a mensagem. Estados `sending`, `pending` ou `unknown` não autorizam repetir cegamente o envio; a chave de idempotência e a reconciliação com o provedor devem ser preservadas.

Os commits que apenas cancelam ou bloqueiam uma mensagem continuam no fluxo original. Criação de lotes e recebimentos assinados não chamam provedores: seus registros, auditoria, notificações e automações são confirmados atomicamente pelo chamador. Os limites específicos dos jobs de automação, comentários e campanhas permanecem nos serviços que os orquestram; não aplique um decorador global de transação a esses fluxos.

## Logs e diagnóstico

Os logs da aplicação são JSON e incluem horário UTC, evento e os campos relevantes da operação. Requisições recebem `X-Request-ID`; um identificador de entrada de até 64 caracteres, limitado a letras, números, ponto, hífen e sublinhado, pode ser reutilizado. Identificadores inválidos são substituídos.

O evento `http_request_completed` registra endpoint, método, status, duração e conta autenticada. O endpoint de saúde não gera esse evento em respostas de sucesso. O gateway `/api/backend` preserva o identificador retornado pelo backend para consulta no painel de rede do navegador.

`delivery_committed` e `delivery_commit_failed` incluem canal, conta, registro e etapa. Para eventos novos, utilize `observability.event()` e seus campos permitidos. Não registre conteúdo de mensagens, JSON de entrada, query strings, cookies, senhas, tokens ou respostas brutas de provedores. Exceções não tratadas registram classe e localização dos frames, sem reproduzir a mensagem da exceção, que pode conter credenciais.

O nível pode ser configurado com `LOG_LEVEL`, por exemplo `INFO` ou `WARNING`.

## Contratos da API

Instale as dependências de desenvolvimento e gere os artefatos:

```bash
backend/.venv/bin/pip install -r backend/requirements-dev.txt
backend/.venv/bin/python scripts/generate-api-contracts.py
backend/.venv/bin/python scripts/generate-api-contracts.py --check
```

- `docs/api/openapi.json`: inventário das rotas registradas, autenticação, parâmetros e entradas identificadas a partir dos schemas Marshmallow.
- `frontend/src/lib/api.generated.ts`: tipos gerados a partir dos componentes desse contrato.
- `frontend/src/lib/types.ts`: reutiliza os registros gerados nos tipos de contatos, empresas, negócios, tarefas, atividades e etapas; mantém os campos adicionais das visualizações.

As respostas detalhadas cobrem esses seis recursos principais do CRM. Outros endpoints constam no inventário com descrição genérica de sucesso; isso não significa que suas respostas já tenham schemas completos. Entradas declaradas apenas em classes locais ou parsers adicionais precisam ser registradas no gerador quando forem documentadas. Os endpoints de WhatsApp documentam JSON e multipart, e os webhooks documentam os mecanismos de assinatura existentes.

O gerador não conecta ao banco, não usa credenciais de produção e não chama provedores. `apispec` é uma dependência de desenvolvimento; o processo de produção não importa o gerador. Não edite os arquivos gerados manualmente. A verificação de qualidade falha se eles estiverem desatualizados.

## Testes

Fixtures `env` e `pg` ficam em `backend/tests/conftest.py`. Builders, payloads e simuladores compartilhados ficam em `backend/tests/helpers/`; arquivos `test_*.py` não devem importar outros arquivos de teste.

Uma fixture automática bloqueia HTTP real e também reprova tentativas que sejam capturadas pelo código sob teste. A busca de perfis do Instagram é simulada por padrão; testes do adaptador substituem o transporte explicitamente. Configurações de teste não herdam credenciais dos provedores da configuração normal.

```bash
./scripts/check.sh
backend/.venv/bin/python scripts/verify-postgres.py
backend/.venv/bin/python scripts/verify-migrations.py
```

Os testes PostgreSQL usam bancos descartáveis e verificam concorrência de reservas, jobs, envios e sincronização de histórico. Os testes adicionais desta refatoração cobrem os dois endpoints de envio de WhatsApp, multipart, isolamento de conta sem contexto HTTP, falha de persistência antes do envio, enfileiramento de e-mail, logs e geração de contratos.

Estas alterações são de código. Publicar uma nova imagem no Docker é uma etapa separada; a imagem em execução não é alterada ao rodar os testes.
