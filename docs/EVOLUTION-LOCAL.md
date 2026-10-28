# Evolution API local no Mac

Instalação em 27/10/2026: Evolution API 2.3.7, PostgreSQL 16.11 e Redis 7.4.7 em Docker, com imagens ARM64. O Docker Engine roda na VM Colima (3 CPUs, 4 GiB de RAM, disco virtual de até 20 GiB). As imagens efetivamente instaladas estão fixadas por SHA256 no `.env` privado. Referência: [instalação oficial](https://github.com/evolution-foundation/docs-evolution/blob/main/v2/en/install/docker.mdx).

## Endereços e integração

- API no Mac: `http://127.0.0.1:8085`.
- API HTTPS: `https://evolution-local.douglasgermano.com`.
- Manager: `https://evolution-local.douglasgermano.com/manager`.
- Túnel exclusivo: `evolution-local` (`97c77a28-448f-4a5d-9bed-bbf59a6f1407`).
- Origem do túnel: `127.0.0.1:8085`, sem porta da API exposta na rede local.
- PostgreSQL e Redis sem publicação de portas no Mac.

Após a migração do Antares para Docker, o CRM usa `EVOLUTION_API_URL=http://evolution-api:8080` pela rede `antares-integrations`. A chave em `~/.config/antares-docker/backend.env` é a mesma `AUTHENTICATION_API_KEY` da instalação privada. A configuração nativa anterior, preservada para reversão, usa `127.0.0.1:8085`. Os webhooks continuam em `https://antares.douglasgermano.com/api/v1/whatsapp/webhook`, com o segredo próprio de cada conta. As duas stacks têm bancos, volumes e túneis separados.

As duas configurações de WhatsApp já existentes foram recriadas na Evolution local, com os mesmos nomes e segredos de webhook. As sessões do provedor externo não foram transferidas. Para parear, entre na Caixa de entrada do Antares e use **Conectar WhatsApp**, depois leia o QR Code em **Aparelhos conectados** no celular. Pareamento e envio/recebimento reais precisam dessa etapa humana.

## Arquivos e operação

O runtime instalado fica em `~/.config/antares-evolution/`, com permissão 700; o `.env` tem permissão 600. As credenciais não ficam no Git. A chave pode ser consultada nesse arquivo privado para entrar no Manager. Nunca cole esse arquivo em logs, tickets ou commits.

O Compose versionável está em `infra/evolution/compose.yaml`; sua cópia instalada fica no runtime privado. O script operacional também é copiado para o runtime, permitindo iniciar a instalação sem depender da release ativa do CRM.

```bash
~/.config/antares-evolution/evolution-local.sh status
~/.config/antares-evolution/evolution-local.sh logs
~/.config/antares-evolution/evolution-local.sh start
~/.config/antares-evolution/evolution-local.sh backup
```

`start` aguarda o Docker e inicia a stack com verificação de saúde. Se o Colima estiver parado, use `brew services start colima` antes. `stop` para os containers preservando os volumes. Nunca use `docker compose down -v` para uma operação rotineira: isso remove os dados.

Os volumes são `antares-evolution_postgres`, `antares-evolution_redis` e `antares-evolution_instances`. Os logs dos containers têm rotação (3 arquivos de até 10 MB por serviço).

O Compose também liga a API à rede externa `antares-integrations`, compartilhada com o CRM. Em uma instalação nova, crie essa rede com `docker network create antares-integrations` antes de iniciar as stacks. Somente a API participa dessa rede; PostgreSQL e Redis permanecem na rede privada da Evolution.

Inicialização ao login:

- `sh.brew.colima`: Docker Engine/VM.
- `com.antarescrm.evolution`: aguarda o Docker e inicia/verifica os containers.
- `com.antarescrm.evolution-tunnel`: mantém o túnel Cloudflare ativo.

As definições ficam em `~/Library/LaunchAgents/`. A configuração do túnel fica em `~/.cloudflared/evolution-local.yml`. Logs da stack e do túnel: `~/.config/antares-evolution/logs/`. O Mac precisa permanecer ligado, acordado, conectado à internet e com a sessão do usuário iniciada. O Cloudflare e o WhatsApp continuam sendo dependências de rede; o processamento da Evolution e seus dados ficam neste Mac.

## Backup e recuperação

`backup` interrompe brevemente apenas a API, gera um dump PostgreSQL, um snapshot Redis e um arquivo das instâncias, e religa a API mesmo em caso de falha. Também copia o `.env` privado e o Compose. Os resultados ficam em `~/.config/antares-evolution/backups/<data-UTC>/` e contêm segredos: mantenha-os privados. O comando é manual; não há agendamento novo de backup.

Antes da troca do provedor, foram salvos o `.env` do CRM, o estado das conexões e um dump completo do banco do CRM em `backups/crm-before-local-20261027T181341Z/`. Esse backup é para reversão da configuração do CRM; não contém sessões do provedor externo.

Para recuperação da Evolution: pare a API, restaure `postgres.dump` no banco Evolution com `pg_restore`, extraia `instances.tar.gz` na raiz do volume de instâncias e restaure o snapshot Redis em um volume Redis vazio antes de iniciar o Redis. Não misture o snapshot RDB com arquivos AOF antigos. Use o `.env` e o Compose do mesmo backup. A restauração não foi executada sobre os dados ativos.

Para reverter apenas o endereço usado pelo CRM: restaure as duas variáveis `EVOLUTION_API_URL` e `EVOLUTION_API_KEY` do `crm.env` privado e reinicie backend e worker. O endereço externo retornava HTTP 404 durante a instalação; voltar ao endereço anterior não garante recuperar o serviço externo.
