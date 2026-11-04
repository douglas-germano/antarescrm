# Grafo de impacto do código

O Neo4j Community armazena o mapa do checkout local do Antares para auxiliar a manutenção.
Não é uma funcionalidade da interface dos clientes. A extração lê arquivos e não importa
a aplicação, conecta ao PostgreSQL ou executa código do projeto.

## Iniciar e consultar

Requisitos: Python 3.10+, Git, Docker Compose e dependências do frontend instaladas
(`cd frontend && npm ci`). O extrator usa o parser TypeScript já presente no projeto;
o cliente Neo4j usa apenas a biblioteca padrão do Python.

Na raiz do repositório:

```bash
python3 scripts/code-graph.py init
python3 scripts/code-graph.py sync
python3 scripts/code-graph.py status
python3 scripts/code-graph.py search ingest
python3 scripts/code-graph.py impact backend/app/services/history.py
python3 scripts/code-graph.py impact --changed --depth 3 --limit 100
```

`init` cria uma senha aleatória uma única vez em `~/.config/antares-code-graph/auth`
(modo 0600, formato `usuário/senha`) e inicia apenas o Compose `antares-code-graph`.
Não há senha padrão nem credenciais versionadas. Não exclua esse arquivo ao reiniciar:
o banco persistente mantém a senha original. `--auth-file` permite outra localização.

Interface visual: http://127.0.0.1:7475/browser/. Na tela de conexão, use
`bolt://127.0.0.1:7688`, usuário `neo4j` e a senha do arquivo privado. HTTP e Bolt estão
publicados apenas em loopback. A imagem está fixada por digest; atualizações exigem
alteração explícita do Compose. Dados e logs persistem em volumes Docker separados.

`sync` analisa os arquivos antes de escrever no Neo4j. Substitui o snapshot do checkout
em uma transação: falhas mantêm o snapshot anterior, e novas sincronizações removem
relações obsoletas sem acumular duplicatas. O caminho absoluto do checkout identifica
seu mapa, permitindo outros worktrees no mesmo serviço. Um bloqueio no registro do mapa
serializa sincronizações concorrentes do mesmo checkout.

`status` informa `fresh`, contagens, hash e horário UTC. Busca e impacto recusam snapshots
cujo fingerprint difere do inventário atual. Mudanças, inclusões e exclusões de fontes,
testes, documentação e regras invalidam o snapshot. Execute `sync` antes de consultar
depois de uma edição. A ferramenta não instala hooks nem atualiza o mapa em background.

## Modelo e evidência

Nós `CodeEntity` têm identificador estável dentro do checkout, `kind`, `name`, `path`,
`line` e `repo`. Tipos: arquivo, função, classe, tipo TypeScript, endpoint e regra.
Arquivos também têm hash SHA-256 e indicação de teste. O conteúdo integral das fontes
não é enviado ao banco. O inventário considera arquivos versionados e novos não ignorados
em `backend/app`, `backend/tests`, `frontend/src`, testes do frontend, `scripts` e documentos
Markdown de `docs`, além dos arquivos de configuração usados pela extração. Arquivos
removidos, symlinks, dependências instaladas, `.env` e dados de clientes ficam fora do mapa.

| Relação | Significado |
| --- | --- |
| `DEFINES` | Arquivo declara função, classe ou tipo |
| `IMPORTS` | Arquivo depende de outro por import/reexport |
| `CALLS` | Chamada Python resolvida por nome ou candidato de chamada HTTP |
| `REFERENCES` | Dependência entre arquivos por chamada resolvida ou candidato HTTP |
| `EXPOSES` | Handler Python declara endpoint Flask |
| `APPLIES_TO` | Regra de negócio se aplica ao arquivo |
| `VERIFIED_BY` | Teste associado à regra por curadoria |
| `DOCUMENTED_BY` | Documento fundamenta a regra |

Cada relação tem `path`, `line` e `origin`: `static`, `inferred` ou `curated`. As linhas
das regras são recalculadas a partir de âncoras únicas. Arquivo ausente ou âncora alterada
faz a sincronização falhar para solicitar atualização da curadoria.

As regras iniciais ficam em [code-graph/rules.json](code-graph/rules.json): isolamento por
workspace, histórico silencioso e persistência da intenção antes da chamada ao provedor.
Para acrescentar uma decisão, registre sua regra, arquivos, testes e documento de origem.
Não coloque segredos ou conteúdo de clientes nas descrições.

## Interpretar o impacto

A consulta percorre imports e referências no sentido inverso e devolve um caminho mínimo
de evidências por arquivo dependente e arquivo alterado. A profundidade padrão é três,
com máximo de seis. `candidate_test` identifica arquivos de teste encontrados. As regras
associadas incluem testes e documentos mesmo quando esses testes não aparecem nos imports.

`truncated=true` indica que existem mais pares de impacto do que o limite retornado;
aumente `--limit` ou consulte arquivos separadamente. As regras são calculadas sobre os
arquivos de entrada e o conjunto de dependentes retornados. `unindexed` lista caminhos
ausentes do inventário (inclusive exclusões já sincronizadas); nesses casos, consulte os
imports antigos no diff e investigue manualmente.

Import não comprova execução nem cobertura. `VERIFIED_BY` não comprova que um teste foi
executado ou passou. A ferramenta não detecta todos os vínculos: injeção de dependência,
reflection, chamadas dinâmicas, aliases locais complexos e métodos de instâncias não são
resolvidos integralmente. As chamadas Python são análise sintática conservadora; não há
análise completa de tipos ou fluxo de dados. O frontend tem imports, reexports, imports
dinâmicos literais, assets diretos e declarações superiores; não há grafo completo de chamadas JS.

As ligações HTTP são inferidas somente para caminhos literais que correspondem exatamente
aos endpoints extraídos: testes Python com `.get/.post/.put/.patch/.delete` e chamadas
frontend importadas diretamente de `lib/api.ts` (`useData`, `useList`, `usePage`, `listAll`,
`post`, `patch`, `remove`). Templates com parâmetros, wrappers, caminhos concatenados e
rotas dinâmicas não são ligados automaticamente. Os endpoints Flask são lidos dos
decoradores `bp` e do prefixo literal de registro; registros dinâmicos precisam de revisão.
Falhas de parsing/import local no frontend interrompem a sincronização, preservando o mapa anterior.

## Consultas visuais no Neo4j Browser

Escolha seu checkout para não misturar worktrees:

```cypher
:param repo => '/Users/douglasgermano/Documents/ChatGPT/antarescrm'
```

Mostrar dependências do histórico:

```cypher
MATCH p=(f:CodeEntity {repo: $repo, id: 'backend/app/services/history.py'})
        -[:IMPORTS|REFERENCES]->(dependency)
RETURN p LIMIT 60;
```

Mostrar regras e evidências:

```cypher
MATCH p=(r:CodeEntity {repo: $repo, kind: 'rule'})
        -[:APPLIES_TO|VERIFIED_BY|DOCUMENTED_BY]->(e)
RETURN p;
```

## Operação e validação

### Compartilhamento temporário

Para uma consulta remota sem acesso de escrita ao banco:

```bash
python3 scripts/code-graph.py sync
python3 scripts/code-graph-share.py --hours 8
```

O comando mantém uma página de consulta em memória com o snapshot atual do Neo4j e
inicia um Quick Tunnel separado. Imprime um link HTTPS com caminho aleatório de acesso.
Quem receber o link pode consultar o mapa; mantenha-o privado. Não há credenciais do
Neo4j na página, endpoints de escrita ou acesso ao sistema de arquivos. A página não
atualiza seu snapshot durante a sessão. O banco continua publicado apenas em loopback.

O processo termina o túnel ao expirar (padrão oito horas, máximo 24) ou receber Ctrl+C/SIGTERM.
O Mac precisa permanecer ligado e conectado. URL, expiração e PIDs ficam no arquivo
privado `.local-services/code-graph-share.json`. Para encerrar uma sessão em background,
envie SIGTERM ao PID desse processo. `cloudflared` deve estar instalado. A página tem
busca por arquivos/símbolos, filtros de testes/regras e navegação pelas relações e evidências.

### Serviço local

Parar preservando dados:

```bash
CODE_GRAPH_AUTH_FILE="$HOME/.config/antares-code-graph/auth" \
  docker compose -f infra/code-graph/compose.yaml stop
```

Para iniciar novamente, execute `init`. Não use `down -v` para manutenção habitual:
isso remove os volumes. Para backup, pare o serviço e copie o volume `antares-code-graph_data`
com as credenciais privadas guardadas separadamente. O mapa também pode ser reconstruído
do código e da curadoria com `sync`.

Os testes comuns não precisam de Neo4j. A validação opcional usa o banco local em uma
partição identificada por um repositório temporário, removida ao concluir:

```bash
CODE_GRAPH_INTEGRATION=1 backend/.venv/bin/python -m pytest -q backend/tests/test_code_graph.py
./scripts/check.sh
```

Os testes cobrem imports relativos e reexports, HTTP inferido, aliases TypeScript, CSS,
imports dinâmicos, freshness, âncoras inválidas, erros retornados com HTTP 202, idempotência,
rollback e remoção de arquivos. O serviço não é necessário para executar o CRM.

Referências: [Docker Compose do Neo4j](https://neo4j.com/docs/operations-manual/current/docker/docker-compose-standalone/)
e [Query API](https://neo4j.com/docs/query-api/current/query/).
