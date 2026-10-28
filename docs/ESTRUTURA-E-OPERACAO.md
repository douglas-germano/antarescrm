# Estrutura e operação

## Limites da aplicação

O layout raiz fornece notificações. Somente `(app)/layout.tsx` monta `SessionProvider`, que busca a sessão e
configura o workspace. Funis, formulários, agendas e aprovações públicas não participam dessa autenticação.
Evite listas manuais de caminhos públicos em providers globais: novas rotas públicas devem funcionar por construção.

As rotas HTTP validam entrada/permissões e chamam serviços. Os filtros de listagem de contatos, tarefas e negócios
ficam em `services/crm_lists.py`. A criação e alteração de projetos ficam em `services/projects.py`.

## Contratos e carregamento

`lib/types.ts` define contratos explícitos para sessão, contatos, empresas, negócios, etapas, atividades e tarefas.
`api`, `post`, `patch` e `useData` usam `unknown` por padrão: quem consome uma resposta precisa informar seu contrato.
O tipo `Row` permanece marcado como legado para componentes configuráveis e módulos ainda não migrados.
Ele não deve ser a base de novos contratos de domínio.

`usePage` busca apenas a página exibida, reinicia a posição quando filtros mudam e corrige a posição após exclusões.
Contatos, tarefas e CRM filtram no servidor. Os totais financeiros e por etapa do CRM consideram todo o conjunto
filtrado, independentemente da página. O seletor de origem recebe os valores disponíveis da conta.
`useList` fica para listas completas de opções/recursos pequenos e limita a três requisições simultâneas.
Novas tabelas volumosas devem usar `usePage`; não use `listAll` para contornar paginação.

As visualizações do funil ficam em `components/crm/deal-views.tsx`. Os estilos antes concentrados em `modules.css`
ficam em quatro arquivos sob `app/styles/`; os imports mantêm a ordem original da cascata.

## Desenvolvimento

`./scripts/dev.sh` usa `backend/.env.development`, PostgreSQL local isolado, portas 5003/3003 e `.next-dev`.
Não herda credenciais de integrações do shell ou do `.env` da produção. Integrações de teste precisam ser
configuradas expressamente no arquivo de desenvolvimento. Anexos de desenvolvimento ficam em
`.local-services/dev/project-files`. O banco deve existir antes de iniciar.

## Releases locais

`deploy-prod.sh` delega para `scripts/deploy.py`. O padrão é **prepare**, sem publicação.
Cada release tem dependências e build próprios; os serviços continuam usando a versão ativa até a ativação.
Credenciais permanecem nos arquivos persistentes e nos ambientes dos LaunchAgents; o diretório da release é privado.
Portas, política de envio do worker, logs e diretório de anexos são preservados ao trocar de release.

A ativação exige a versão preparada, um backup validado e o bloqueio exclusivo de deploy. Ela remove os LaunchAgents
para impedir reinício por KeepAlive enquanto migra. Backend e frontend são iniciados antes do worker; os testes incluem
saúde do banco/API, login e recusa de acesso anônimo ao gateway.

Uma falha sem mudança de schema permite retomar os LaunchAgents anteriores (código, dependências e build juntos).
Uma falha após iniciar uma mudança de schema mantém os serviços parados. Examine a migração e o banco antes de
retomar; a configuração anterior fica em `previous-services.plist`. Não restaure o banco sobre dados recentes sem
avaliação explícita. O backup não é uma política de rollback automático.

## Verificações

```bash
./scripts/check.sh
backend/.venv/bin/python scripts/verify-migrations.py
backend/.venv/bin/python scripts/verify-postgres.py
cd frontend
NEXT_DIST_DIR=.next-check npm run build
npx playwright install chromium
npm run test:browser
```

Os testes PostgreSQL criam e removem bancos descartáveis. Os testes de navegador iniciam um Next isolado em porta
livre e uma API de fixtures; não acessam contas reais nem enviam mensagens externas. Incluem navegação anônima em
funis, proteção de páginas internas, domínio personalizado e paginação/busca de tarefas e negócios em desktop e celular.

`.github/workflows/check.yml` executa lint, formatação, testes Python, tipos TypeScript, testes Node, migrações,
concorrência PostgreSQL, build e navegador. A execução remota depende de enviar o workflow ao GitHub.

Os testes de WhatsApp usam adaptadores falsos para validar ingestão, deduplicação, supressão, envio durável,
resultados ambíguos e mídia. Eles não confirmam disponibilidade ou conexão real do provedor.
