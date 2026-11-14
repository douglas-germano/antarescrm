# Cobrança com Asaas

Assinatura mensal por conta (workspace), com teste grátis, Pix/boleto/cartão na fatura hospedada do Asaas e
bloqueio de escrita por inadimplência. Contas de clientes de uma agência seguem a assinatura da agência.

## Regras de acesso
- **Sem registro de assinatura** (contas antigas e internas): acesso total, nunca bloqueadas.
- **Teste** (`trialing`): acesso total por `BILLING_TRIAL_DAYS`; depois, somente leitura.
- **Ativa** (`active`): acesso total.
- **Em atraso** (`past_due`): acesso total por `BILLING_GRACE_DAYS`; depois, somente leitura.
- **Cancelada**: somente leitura.
- Somente leitura = GET liberado; criar/alterar responde `402 subscription_required`. Login, troca de conta e
  `/billing/*` continuam funcionando.
- Novos cadastros iniciam o teste só quando `BILLING_ENABLED=true`.

## Ativação
1. No `backend.env` privado: `BILLING_ENABLED=true`, `ASAAS_ENV`, `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`
   (valor longo e aleatório) e `BILLING_PRICE_BRL`. Teste primeiro com `ASAAS_ENV=sandbox` e a chave do sandbox.
2. No painel do Asaas, em Integrações → Webhooks, cadastre
   `https://antares.douglasgermano.com/api/v1/billing/asaas/webhook`, o mesmo token em "Token de autenticação"
   e os eventos de cobrança (`PAYMENT_*`) e de assinatura (`SUBSCRIPTION_*`).
3. Aplique a migração `20261113_billing` e reinicie backend e worker.

## API
- `GET /api/v1/billing`: estado, acesso, fim do teste, próximo vencimento, link da fatura.
- `POST /api/v1/billing/subscribe` (`owner`/`admin`): `{ "cpf_cnpj": "..." }`. Cria cliente e assinatura mensal no
  Asaas; a primeira cobrança vence ao fim do teste (mínimo amanhã). O cliente escolhe Pix, boleto ou cartão na fatura.
- `POST /api/v1/billing/asaas/webhook`: autenticado por `asaas-access-token`; idempotente por id de evento.

## Limites conhecidos
- O bloqueio vale para chamadas autenticadas da interface. Tokens de API/MCP, o worker de automações e as páginas
  públicas (formulários, funis, agendas) ainda não consultam o estado da assinatura.
- Não há tela de assinatura no frontend; o fluxo hoje é pela API.
- Pontos de atenção do sandbox do Asaas: valide em ambiente de teste Pix, boleto, atraso e cancelamento antes de produção.
