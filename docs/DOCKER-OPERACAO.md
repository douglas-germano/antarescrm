# Antares CRM no Docker

Migração ativada em 27/10/2026, aproximadamente às 14h32 (America/Cuiaba), mantendo `https://antares.douglasgermano.com`.

## Instalação ativa

A stack `antares-crm` roda no Docker Engine do Colima, no Mac:

| Serviço | Função | Acesso no Mac |
| --- | --- | --- |
| frontend | Next.js | `127.0.0.1:3002` |
| backend | Flask/Gunicorn | `127.0.0.1:5002` |
| postgres | PostgreSQL 16 | Sem porta publicada |
| worker | Automações, mantendo `--no-dispatch` | Sem porta publicada |
| tunnel | Cloudflared, túnel original do Antares | Saída para Cloudflare |

O backend e o worker alcançam a Evolution em `http://evolution-api:8080` pela rede `antares-integrations`. Apenas a API da Evolution participa dessa rede compartilhada; os bancos da Evolution e do CRM ficam nas respectivas redes de cada stack. A Evolution mantém seu próprio túnel e seus volumes.

Os volumes persistentes do CRM são `antares-crm_postgres` e `antares-crm_project-files`. Não use `down -v` para manutenção: isso remove os dados.

O runtime privado fica em `~/.config/antares-docker/`. Os arquivos `.env`, `backend.env`, `frontend.env` e `tunnel.json` contêm credenciais e ficam fora do Git. O backend recebe as chaves originais da aplicação, JWT e integrações; as senhas dos usuários e os dados criptografados foram preservados. A conexão do banco é sobrescrita pelo Compose para apontar para o PostgreSQL do container.

O banco nativo do macOS foi mantido como cópia anterior à migração. Ele não recebe as novas gravações da aplicação. Os antigos LaunchAgents foram desativados e arquivados em `legacy-launchagents/`, dentro do runtime privado, evitando iniciar duas instalações no próximo login.

## Operação

```bash
~/.config/antares-docker/antares-docker.sh status
~/.config/antares-docker/antares-docker.sh logs
~/.config/antares-docker/antares-docker.sh start
~/.config/antares-docker/antares-docker.sh backup
```

`start` aguarda o Docker e verifica a saúde dos serviços que têm healthcheck. `stop` para a stack e preserva os volumes. Os comandos de início, parada e backup usam um lock para não se sobreporem.

Inicialização ao login:

- `sh.brew.colima` inicia o Docker Engine.
- `com.antarescrm.docker` inicia a stack e termina com código zero quando ela está pronta; esse LaunchAgent não precisa permanecer executando.
- `com.antarescrm.docker-backup` executa o backup diariamente às 03h00 no horário do Mac.

O Docker reinicia os containers com `unless-stopped`. O worker tem healthcheck baseado no heartbeat do banco, verifica que não há erro recente e confirma que o dispatch continua desabilitado. O tunnel é conferido pelo endereço público e pelos logs de conexão. Logs dos containers têm rotação de 3 arquivos de até 10 MB por serviço.

O Mac precisa estar ligado, acordado, conectado e com a sessão iniciada. A execução de um agendamento enquanto o Mac está desligado não foi testada. `start` não altera as políticas de suspensão do macOS.

## Backup

O backup interrompe brevemente frontend, backend e worker para manter banco e arquivos consistentes. Ele gera:

- `database.dump`: dump completo do PostgreSQL.
- `project-files.tar.gz`: anexos dos projetos.
- Configurações e credenciais da instalação, incluindo o túnel.
- `backup.json`: data, tamanho e resultado da verificação.

Os serviços são retomados após a cópia. O dump é restaurado em um banco temporário do próprio PostgreSQL, validado e o banco temporário é removido. O banco ativo não é restaurado por essa verificação.

As cópias ficam em `~/.config/antares-docker/backups/`, com permissões privadas. O status de sucesso fica em `status/latest.json`, montado somente para leitura no backend para a tela de operação. Não há remoção automática dos backups. Uma cópia no mesmo Mac não protege contra perda física do disco.

O backup anterior à troca está no diretório `backups/cutover-<data-UTC>/`; o primeiro backup do Docker, com restauração comprovada, está em `backups/antares-20261027T183310Z-387f08/`.

## Recuperação e reversão

Antes de recuperar dados, interrompa o frontend, o backend, o worker e o túnel para impedir novas gravações. Faça uma cópia do estado atual. Restaure `database.dump` no PostgreSQL e `project-files.tar.gz` no volume de anexos usando as configurações e chaves do mesmo backup. Ajuste a propriedade dos anexos para UID/GID `10001:10001` antes de iniciar o backend. Inicie e valide a aplicação antes de reabrir o túnel.

Para voltar à instalação nativa após a aplicação ter recebido novas gravações no Docker, é necessário exportar o banco atual do Docker e os anexos atuais e restaurá-los no destino nativo antes de iniciar os serviços anteriores. Somente reiniciar os LaunchAgents antigos exporia uma cópia desatualizada dos dados. Os plists originais, a configuração do túnel e o ambiente nativo foram preservados no runtime privado.

O script nativo `scripts/deploy-prod.sh activate` bloqueia a ativação enquanto o marcador `~/.config/antares-docker/ACTIVE` existe. Isso evita reabrir acidentalmente a instalação nativa contra o banco antigo. A reversão completa após novas gravações não foi executada; a ativação teve verificações e mecanismo de retorno em caso de falha.

## Versão e futuras atualizações

A primeira imagem usa o backend da release `20261022T233440Z-20238f` e exatamente o frontend já compilado dessa release, com BUILD_ID `_g8A7aMiGV4utgtqlHqxy`. As dependências de execução foram instaladas para Linux ARM64. As alterações sem commit do checkout foram preservadas e não entraram nesta migração.

Os Dockerfiles e o Compose versionáveis ficam em `infra/antares/`. O contexto de construção privado usado na migração fica em `~/.config/antares-docker/build-context/`; ele não contém arquivos `.env`. O Dockerfile do frontend consome um build `.next-public` previamente validado; ele não recompila o código fonte.

Para publicar código novo, prepare e teste uma nova release, compile o frontend, monte um novo contexto sem credenciais e construa imagens com tags novas. Faça backup, aplique eventuais migrações de banco em manutenção e atualize as referências de imagem no `.env` privado. Use o helper `start` e valide o endereço público. Não sobrescreva uma tag antiga nem use o contexto congelado desta migração para publicar alterações novas. Alterações no Compose versionável precisam ser copiadas para o runtime instalado antes de `start`.

## Evidências da migração

- 297 testes de backend passaram no código original, com 87,46% de cobertura.
- 297 testes passaram também dentro do container; 14 testes específicos de PostgreSQL passaram em banco descartável.
- Typecheck e os 29 testes de gateway passaram.
- As 50 tabelas tiveram contagens e hashes de conteúdo idênticos na cópia final, antes de retomar os serviços.
- Os dois anexos foram conferidos byte a byte pelo endpoint autenticado de download.
- Sessão autenticada, bloqueio de troca indevida de conta, dois formulários públicos e arquivos JavaScript da release foram conferidos no endereço público.
- Nenhum envio de mensagem ou submissão de lead foi realizado na verificação.
- O backup do Docker foi restaurado e validado em um banco descartável.

Relatórios privados: `database-parity.json`, `staging-verification.json`, `production-verification.json`, `migration.json` e `logs/`. O primeiro atesta o estado no momento da troca; alterações posteriores feitas por usuários, webhooks e worker são esperadas.
