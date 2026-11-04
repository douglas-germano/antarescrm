# Frontend React, Vite e TanStack Start

O frontend utiliza React 19, Vite, TanStack Router e TanStack Start. O servidor de produção é gerado pelo Nitro em `frontend/.output/`. Next.js e suas configurações foram removidos das dependências e da execução do projeto.

## Organização

- `frontend/src/routes/`: declarações de rotas, layouts e endpoints HTTP.
- `frontend/src/screens/`: telas React reaproveitadas da aplicação.
- `frontend/src/styles/`: estilos globais e dos módulos.
- `frontend/src/routeTree.gen.ts`: árvore gerada pelo TanStack; versionada para permitir a checagem de tipos antes do build.
- `frontend/src/server.ts`: entrada HTTP e proteção de domínios personalizados.
- `frontend/src/lib/bff.ts`: gateway para o Flask, com JWTs em cookies HttpOnly.

As telas de listagem com detalhes, como `/projetos` e `/projetos/:id`, são rotas irmãs. Apenas os layouts compartilhados renderizam `Outlet`; uma página de lista não envolve a página de detalhes.

## Executar

Requer Node.js 22.22 ou superior.

```bash
cd frontend
npm ci
npm run build
npm run typecheck
npm run test:gateway
npm run test:browser
npm start -- --host 127.0.0.1 --port 3003
```

Para desenvolvimento com banco e API isolados, utilize `./scripts/dev.sh` na raiz. O script continua reservando as portas 3002/5002 para produção. O comando `npm run dev` inicia somente o frontend Vite.

## Comportamento preservado

Os endereços de páginas, gateways, formulários, agendamentos, aprovações, webhooks e callback do Instagram permanecem iguais. Os redirecionamentos de `/whatsapp`, `/agendamentos` e `/operacao` foram mantidos, incluindo o identificador da conversa em `/whatsapp`.

O login continua usando cookies HttpOnly, renovação pelo gateway e autorização no Flask. A rota `/api/public/entry` fornece somente a indicação de existência de sessão e o identificador do funil público do domínio atual; não retorna tokens nem dados de usuário. Ela permite revalidar o acesso durante a navegação e o retorno pelo histórico do navegador. Domínios de clientes continuam sem acesso ao CRM e ao gateway autenticado. Respostas dinâmicas recebem `Cache-Control: no-store`.

SWR continua responsável pelo cache e pela atualização dos dados. O backend, o banco e os provedores externos não exigem migração por causa desta troca de frontend.

## Navegação sem recarga de página

Links internos utilizam o router React. A intenção de navegação por mouse, foco ou toque antecipa o carregamento do código. Os loaders de telas principais aquecem as mesmas chaves de dados usadas pelo SWR antes da troca de tela. A navegação preserva o shell e mantém o conteúdo anterior enquanto prepara o destino; uma barra fina aparece apenas quando a transição demora mais de 180 ms. Telas já preparadas reutilizam o cache do SWR, que continua revalidando os dados.

Na primeira busca, os estados de dados usam espaços reservados, sem o aviso central de “Carregando…”. Falhas podem ser consultadas novamente sem recarregar o documento. A abertura de conversa a partir de Contatos e o redirecionamento antigo da agenda também usam navegação interna.

O login, a saída, a troca de conta e as autorizações externas podem continuar exigindo uma navegação completa para reiniciar o estado da sessão ou visitar o provedor. Pré-carregamento e cache não eliminam a espera inicial pela rede. Os parâmetros da URL mantêm valores textuais como `new=true` e `modelo=0`, incluindo acentos e parâmetros repetidos.

## Publicação

O Dockerfile do frontend consome `frontend/.output/`, sem depender de uma instalação do Next.js. O preparador de releases compila o novo bundle e converte a execução do frontend para `frontend/scripts/start.mjs`, mantendo host e porta da definição anterior. O launcher lê os arquivos de ambiente de produção sem sobrescrever variáveis fornecidas pelo serviço.

Editar o checkout ou executar os testes não altera a aplicação publicada. Uma publicação deve utilizar a infraestrutura de produção em uso e o novo bundle validado. Os registros históricos de releases anteriores continuam descrevendo os builds Next.js existentes naquelas versões.

## Validação

A suíte de navegador usa uma API de fixtures e portas livres. Verifica sessão, logout, cookies HttpOnly, proteção contra origem externa, URLs e payloads de webhooks, formulários, navegação com parâmetros, redirecionamentos, metadados legais, telas de detalhes, histórico em domínio personalizado, paginação, layouts responsivos, campanhas, negócios na caixa de entrada e notificações entre abas. Não envia mensagens a provedores nem acessa contas reais.

## Estado de produção

Publicado no Docker em 30/10/2026 às 18h41 (America/Cuiaba), com verificação pública concluída às 18h43. Imagem `antares-crm-frontend:tanstack-20261030t223023z`. Operação e reversão em [DOCKER-OPERACAO.md](DOCKER-OPERACAO.md).
