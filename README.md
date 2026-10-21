# Antares CRM

CRM multi-tenant com contatos, empresas, funil de vendas, tarefas, atividades, relatórios e
WhatsApp via Evolution API. Base de código reaproveitada do projeto *Minha Marcenaria*
(auth/JWT, helpers, módulo de WhatsApp, kit de UI e gateway BFF), sem os módulos específicos
daquele domínio (projetos, financeiro, cobrança, assistente de IA).

- **Backend** — Flask + SQLAlchemy + Alembic + PostgreSQL (`backend/`)
- **Frontend** — Next.js 15 (App Router) + React 19 + SWR + Recharts (`frontend/`)
- Sem Docker: tudo roda localmente.

## Primeira execução

```bash
createdb antarescrm
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # defina SECRET_KEY e JWT_SECRET_KEY
.venv/bin/flask --app run db upgrade
DEMO_PASSWORD='uma-senha-longa' .venv/bin/flask --app run seed-demo   # opcional: workspace "demo"
cd ../frontend && npm install
```

## Rodar

```bash
./scripts/dev.sh        # API em :5002, web em :3002 (ajustável com API_PORT / WEB_PORT)
```

Acesse http://localhost:3002 — workspace `demo`, e-mail `admin@antarescrm.local`.

## Estrutura do código

```
backend/app/
  models/      modelos SQLAlchemy por domínio (base, tenancy, crm, whatsapp, automation, instagram, communications, booking, projects)
  schemas/     schemas Marshmallow (base, auth, crm, projects; growth é importado direto para evitar ciclo com services)
  routes/      blueprints HTTP finos; crm/, growth/ e projects/ são pacotes divididos por recurso
  services/    regras de negócio e integrações (opportunities, form_submission, rules, projects, whatsapp, instagram, ...)
  errors.py, security.py   handlers de erro JSON, callbacks JWT, headers e checagem de config de produção
  common.py, access.py, config.py, extensions.py, cli.py
frontend/src/
  app/         rotas Next.js (App Router)
  components/  ui.tsx, blocks.tsx, fit.tsx, providers.tsx (compartilhados) + pastas por feature:
               auth, layout, contacts, settings, booking, automations, inbox, projects, whatsapp
  lib/         api, bff (gateway), format, types
```

Convenção: rotas só validam a entrada e chamam um service; regra de negócio e consultas ficam em `services/`.

Qualidade (ruff, pytest com cobertura, typecheck e testes do gateway):

```bash
./scripts/check.sh
```

## Funis de páginas e formulários

- **Formulários** (`/formularios/<id>`): construtor com prévia ao vivo. Campos de texto, e-mail, telefone, link, número,
  data, listas, escolha única/múltipla, caixa de seleção e blocos de layout (título, texto, divisória); largura inteira ou
  meia linha, ordem por arraste, condições, cores, fonte, arredondamento, botão, logotipo, texto de consentimento e
  ação após o envio (mensagem ou redirecionamento). Tudo é validado no servidor (`services/form_design.py`).
- **Funis** (`/funis`): sequência de páginas feitas de blocos (título, texto, imagem, vídeo, botão, formulário, lista,
  depoimento, perguntas, contagem regressiva, espaço). Modelos prontos (captura, vendas, em branco), publicação,
  duplicação e métricas por página (visitantes, conversões, abandono). A página pública fica em `/p/<funil>/<página>`;
  o formulário embutido reaproveita a captura existente (contato, negócio e automações). Os blocos são dados
  validados em `services/funnel_blocks.py` (links só `https`, sem HTML livre) e renderizados como nós React.
- Publicar um funil ativa os formulários usados nas suas páginas.

## Domínios personalizados

Em **Configurações → Domínios** cada conta cadastra domínios próprios (ex.: `paginas.cliente.com.br`) para publicar
funis, formulários e agendas. Fluxo: o cliente cria um registro **TXT** (`_antares-verify.<domínio>`) que prova a
posse e um **CNAME** (ou A, para domínio raiz) para a plataforma; **Verificar agora** consulta o DNS por DNS-over-HTTPS
(sem dependência extra). O domínio só serve páginas depois de comprovada a posse, e só do próprio workspace: o gateway
Next.js envia o `Host` ao Flask (`X-Custom-Domain`) e os endpoints públicos recusam conteúdo de outras contas.
Em domínios de clientes só as páginas públicas respondem (`/p`, `/f`, `/agendar`, `/agendamento`, `/aprovacao`,
`/api/public`); CRM, login e o gateway autenticado ficam apenas no domínio da plataforma. A raiz `/` mostra o funil
escolhido para o domínio (`src/middleware.ts`).

HTTPS e roteamento são infraestrutura, fora do código:
- **Cloudflare for SaaS** (recomendado para o túnel atual): ative *Custom Hostnames* na zona da plataforma, defina
  `CLOUDFLARE_API_TOKEN` e `CLOUDFLARE_ZONE_ID` e o Antares registra o domínio e acompanha o certificado após a
  verificação. O `ingress` do cloudflared precisa de uma regra final para `http://127.0.0.1:3002` (hoje o fallback é
  `http_status:404` e só o hostname da plataforma é atendido).
- **Sem provedor**: termine o TLS em um proxy com certificado sob demanda (ex.: Caddy `on_demand_tls`) usando
  `GET /api/v1/public/domains/resolve?host=<domínio>` como endpoint de autorização (200 = emitir).
- Variáveis em `backend/.env.example`. A API só deve ser alcançável pelo gateway, pois confia no cabeçalho `X-Custom-Domain`.

## Multi-tenant

Cada workspace tem seus próprios dados; toda consulta é filtrada por `workspace_id` e um UUID de
outro workspace retorna 404. Um workspace pode ter vários usuários, com papéis `owner`, `admin` e `member`.
Administradores da agência podem acessar contas-filhas; membros precisam de concessão explícita.
O campo `title` é um rótulo de cargo, separado das permissões.

## WhatsApp (Evolution API)

Defina no `backend/.env`: `EVOLUTION_API_URL`, `EVOLUTION_API_KEY` e `WHATSAPP_WEBHOOK_BASE_URL`
(URL do backend alcançável pela Evolution, sem `/api/v1`). Em **WhatsApp → Conectar WhatsApp** o
sistema cria a instância do workspace, configura o webhook e mostra o QR Code. Mensagens
recebidas são vinculadas ao contato pelo telefone (aceita variação do 9º dígito) ou criam um novo.
Para receber webhooks localmente, exponha a porta da API com um túnel (ex.: Cloudflare Tunnel).

## Estrutura da API (`/api/v1`)

`auth`, `users`, `workspace`, `companies`, `contacts` (+ `/timeline`), `pipeline/stages`,
`opportunities` (+ `/close`), `activities`, `tasks`, `dashboard`, `reports/*`, `calendar`,
`forms`, `funnels` (+ `/steps`, `/stats`, `/duplicate`), `whatsapp/*`. Erros: `{error:{code,message,details?}}`; listas: `{items,page,per_page,total,pages}`.

## Domínio público e Cloudflare Tunnel

URL: https://antares.douglasgermano.com

Túnel dedicado `antarescrm` (`ab47299c-9f4f-4ac0-9758-058b489fc1e2`), com
configuração em `~/.cloudflared/antarescrm.yml`. O hostname encaminha para
`http://127.0.0.1:3002`; o Next.js acessa a API internamente em `127.0.0.1:5002`.
Credenciais ficam fora do repositório, em `~/.cloudflared/`.

Os serviços `com.antarescrm.backend`, `com.antarescrm.frontend` e
`com.antarescrm.tunnel` são LaunchAgents em `~/Library/LaunchAgents/`, com início
automático no login do usuário e reinício em caso de falha. O backend usa Gunicorn;
o frontend usa Next.js em produção, com build em `.next-public/`.
A URL e os cookies HTTPS ficam em `frontend/.env.production.local` (ignorado pelo Git)
e nas variáveis do LaunchAgent. Logs em `.local-services/`.

O Mac precisa permanecer ligado, conectado e com a sessão do usuário iniciada.
Não execute `scripts/dev.sh` nas mesmas portas enquanto estes serviços estiverem ativos.

Recompilar o frontend após alterações:

```bash
cd frontend
NEXT_DIST_DIR=.next-public npm run build
launchctl kickstart -k gui/$(id -u)/com.antarescrm.frontend
```

Reiniciar um serviço (substitua `frontend` por `backend` ou `tunnel`, se necessário):

```bash
launchctl kickstart -k gui/$(id -u)/com.antarescrm.frontend
```

Parar ou iniciar o túnel manualmente:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.antarescrm.tunnel.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.antarescrm.tunnel.plist
```

## Acompanhamento comercial

A visão geral prioriza negócios com ações atrasadas, previsão de fechamento vencida ou sem
próxima ação agendada. O funil permite filtrar essa fila e abrir negócios por link direto.
`GET /api/v1/reports/follow-ups?mine=true` restringe aos negócios do usuário autenticado.
Tarefas com prazo na data local atual permanecem no prazo até o fim do dia.

No contato, o histórico reúne negócios, tarefas, notas e retornos. É possível registrar notas,
agendar retornos vinculados a negócios e concluir atividades pendentes. Nenhuma mensagem é
enviada automaticamente. Filtros por responsável, origem e empresa podem ser salvos como
visões locais: até oito por conta e workspace, disponíveis somente no navegador atual.
As melhorias reutilizam os modelos existentes e não exigem migração de banco.

Validação: `cd backend && .venv/bin/python -m pytest -q`.

## Evolução para uso interno

A implementação de operação, formulários configuráveis, reservas públicas, múltiplos funis,
condições de automação e visões persistidas está detalhada em
[docs/IMPLEMENTACAO-USO-INTERNO.md](docs/IMPLEMENTACAO-USO-INTERNO.md).

Worker local (a partir de `backend/`):

```bash
.venv/bin/flask --app run run-worker --no-dispatch
```

O processamento padrão não entrega mensagens aos provedores. Para habilitar entrega, configure
os canais por conta e use `--dispatch`. Bloqueios por contato/canal continuam sendo respeitados.

Backup com restauração de prova em banco descartável (a partir da raiz):

```bash
backend/.venv/bin/python scripts/backup.py --verify
backend/.venv/bin/python scripts/manage-services.py prepare
```

Após aplicar as migrações e publicar a versão, substitua `prepare` por `install` para registrar
worker e backup diário no macOS. O padrão instala o worker sem envio externo de mensagens.
