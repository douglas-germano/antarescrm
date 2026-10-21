# Implementação para uso interno — 21/10/2026

Direção confirmada pelo usuário: uso interno da própria empresa. Esta entrega amplia a operação comercial atual; não representa equivalência completa ao HighLevel.

## Entregue no código

- **Operação:** painel `/operacao` com heartbeat, sinalização de falhas, fila de etapas e mensagens, disponibilidade dos canais e estado do último backup. A atualização ocorre a cada 15 segundos enquanto a página está aberta.
- **Worker:** `run-worker` registra o resultado de cada ciclo. O padrão é `--no-dispatch`: processa tarefas/retornos e enfileira mensagens, sem entregá-las aos provedores. O envio depende de ativação expressa com `--dispatch` e configuração dos canais.
- **Backup:** `scripts/backup.py --verify` gera arquivo privado, restaura em banco descartável, confere tabelas e remove somente esse banco de teste. Não restaura por cima do CRM. Não remove backups antigos automaticamente.
- **Supervisão:** `scripts/manage-services.py prepare` gera LaunchAgents para worker e backup diário às 03h, horário local do Mac. `install` efetiva a instalação após aplicar as migrações. A configuração e os serviços atuais de frontend/backend/túnel são preservados.
- **Formulários:** editor de perguntas de texto, texto longo, número, data, seleção e checkbox; obrigatoriedade, exibição condicional e mapeamento de respostas para campos personalizados. Respostas e UTMs são armazenadas por solicitação. Nome da empresa e cor principal são configuráveis.
- **Agendamento:** criação de agendas, múltiplos intervalos por dia, antecedência, horizonte, duração, intervalo entre reservas, responsável e ativação pública. Links em `/agendar/{id}` e gerenciamento por link assinado em `/agendamento/{token}`. Reserva, cancelamento e reagendamento atualizam a atividade interna. A consulta de disponibilidade usa o fuso da conta; o PostgreSQL serializa reservas do mesmo responsável entre agendas. Reuniões e ligações manuais ocupam a duração definida na agenda por não possuírem horário final no modelo antigo.
- **Automações:** eventos de contato, formulário, mensagem recebida, agendamento/criação/cancelamento e mudança/encerramento de negócio. Condições todas/qualquer, inclusive campos personalizados e etapa/estado/valor do negócio, disponíveis também por etapa. Ações futuras e mensagens ainda na fila podem ser interrompidas quando o contato responde. Configuração do responsável e interrupção é preservada por execução; ações já agendadas usam seus próprios dados.
- **Preferências de contato:** bloqueio por contato/canal, cancelamento da fila não enviada e verificação no despacho, inclusive no envio direto de WhatsApp. Remover o bloqueio não reenvia mensagens canceladas.
- **CRM:** múltiplos funis, preservando etapas existentes em “Principal”. Cada novo funil recebe suas etapas. Filtros salvos por usuário/conta ficam no banco e podem ser usados em outros dispositivos; há importação manual das visões antigas do navegador.
- **Relatórios:** corrigida a comparação incorreta entre data e timestamp no relatório mensal. No PostgreSQL, o agrupamento considera o fuso da conta.

## Banco e implantação

Migrações novas, em ordem:

1. `20261021_operations`: formulários, operações, reservas e preferências de contato.
2. `20261021_pipelines`: funis adicionais.
3. `20261021_contact_views`: visões persistidas.

A primeira publicação desta entrega foi realizada em 21/10/2026 às 10h05 (America/Cuiaba). Migrações aplicadas até `20261021_contact_views`; build promovido para `.next-public`. Os registros existentes e o estado de ativação dos formulários foram conferidos antes e depois, sem alterações.

A implantação deve fazer backup do banco, aplicar `flask --app run db upgrade` a partir de `backend/`, promover o build com o frontend parado e reiniciar backend/frontend. Após a migração, `backend/.venv/bin/python scripts/manage-services.py install` instala o worker sem envio de mensagens e o backup agendado. O túnel não precisa ser substituído. Não usar um build de revisão que aponta para API de teste.

A reversão da migração de funis exige nomes de etapas únicos entre os funis do mesmo workspace, pois o esquema anterior tinha essa restrição. O downgrade recusa essa situação em vez de renomear ou apagar dados.

## Limites e próximas etapas

- WhatsApp, SMTP/SMS e sincronização Google/Microsoft dependem de configuração e credenciais. Não houve envio real nem conexão de provedores nesta entrega.
- O adaptador oficial WhatsApp Cloud API, Instagram/Messenger, Google Calendar e Outlook ainda não foram adicionados. O adaptador Evolution existente foi preservado.
- As condições por etapa permitem caminhos condicionais em uma sequência; ainda não há editor gráfico, espera reativa por evento com timeout ou versão rascunho/publicada do fluxo.
- Reservas não enviam confirmação/lembrete de compromisso automaticamente. Há confirmação na página e ações configuráveis pelo evento `booking.created`.
- Formulários não incluem upload de arquivo, assinatura, construtor de layout ou script de incorporação em sites externos.
- Construtor de sites/funis de marketing, pagamento/faturamento, IA, telefonia, reputação e social planner continuam fora desta primeira entrega interna. Cobrança SaaS, white label e cursos foram adiados conforme a prioridade de uso interno.
- A hospedagem continua local. Não foi contratado nem provisionado servidor externo.
- Não foram feitos commit ou push. Os arquivos anteriores sem commit foram preservados.

## Validação

Os testes cobrem campos obrigatórios/ocultos, snapshots e UTMs, isolamento entre usuários e contas, concorrência de captura e reservas, conflitos de calendário, links assinados, cancelamento/reagendamento, interrupção após resposta e bloqueio de comunicação.

Foi realizado backup real seguido de restauração em banco temporário. Os testes de interface usaram exclusivamente o banco de revisão `antares_review_*`, sem inserir leads na base de produção.

Evidências visuais: `output/playwright/operacao-desktop.png` e `output/playwright/agendamento-mobile.png`. No celular, a largura de conteúdo e viewport conferidas foi 390px, sem transbordamento horizontal.

Resultado final desta entrega:

- `cd backend && .venv/bin/python -m pytest -q`: **80 aprovados**, 7 testes exclusivos de PostgreSQL ignorados nesta execução.
- `backend/.venv/bin/python scripts/verify-postgres.py`: **7 aprovados** no PostgreSQL descartável, incluindo concorrência e agrupamento mensal no fuso da conta.
- `backend/.venv/bin/python scripts/verify-migrations.py`: atualização/reversão/atualização com preservação de dados e metadados compatíveis.
- `cd frontend && npm run test:gateway`: **9 aprovados**.
- `npm run typecheck` e build em `.next-public-staging`: aprovados.
- Navegador: configuração da disponibilidade, reserva, link de gerenciamento e cancelamento; formulário condicional com UTMs; criação de outro funil; filtros salvos persistidos após recarregar; criação de automação com condição e interrupção após resposta. Console sem erros na conferência final.
- `scripts/backup.py --verify`: backup real restaurado com sucesso em banco temporário.
- LaunchAgents do worker e backup instalados em produção. Worker ativo com `--no-dispatch`; backup diário às 03h (horário local), com a primeira execução pelo próprio serviço concluída e restauração isolada verificada.
- Serviços e banco temporários de revisão encerrados após os testes.

## Simplificação da navegação — 21/10/2026

- Caixa de entrada reúne Evolution/WhatsApp, e-mail e SMS na mesma lista, com busca, canal, abertas/encerradas e atualização automática. O atendimento WhatsApp usa os componentes completos de histórico, mídia, anexos, responsável, vínculo ao contato e gerenciamento da conexão. Disparos e estado dos canais ficam recolhidos.
- Atividades reúne calendário, lista de tarefas/atividades/reservas e a aba Links de agendamento. Reservas usam a atividade já existente, sem uma segunda cópia do evento. Os detalhes mostram contato, início e fim; reagendamento e cancelamento permanecem sincronizados.
- Menus separados de WhatsApp e Agendamentos removidos. Links antigos redirecionam para as áreas unificadas, preservando o identificador da conversa.
- Validação: 81 testes backend aprovados, 7 exclusivos de PostgreSQL ignorados nessa execução; gateway com 9 aprovados; build e tipos aprovados. Navegador com banco descartável: conversa WhatsApp, leitura do histórico, retorno à lista no celular, reserva em mês/lista/detalhes, configuração de disponibilidade e redirecionamentos. Largura de 390px sem transbordamento; compositor visível no celular. Nenhuma mensagem externa enviada nos testes.

Publicação da simplificação concluída em 21/10/2026 às 10h16 (America/Cuiaba), build `5wJqKV2qZn988JH7qXYsd`. Backend/frontend reiniciados, registros e ativação dos formulários preservados. Backup com restauração isolada verificada antes da promoção.

Conferência após publicação: `/login` e `/mensagens` responderam HTTP 200; bundles públicos de `/mensagens` e `/agenda` comparados byte a byte com o build local promovido. Saúde do backend OK; frontend, backend, túnel e worker ativos.

## Evolution API — 21/10/2026

Credenciais de acesso obtidas do `.env` do Minha Marcenaria e aplicadas somente ao `.env` privado do Antares. As instâncias existentes do outro projeto foram preservadas; Antares usa sua própria instância e segredo de webhook por conta. O endereço público `/api/v1/whatsapp/webhook` agora encaminha callbacks ao backend, preservando os bytes assinados e os cabeçalhos de autenticação, sem cookies ou credenciais de sessão. O backend valida o segredo da instância.

Build `WrlN7ndZzVOeVyfl5DTJs` publicado. Testes: 11 do gateway e 3 da autenticação de webhook aprovados; build/tipos aprovados; provedor confirmou webhook habilitado, URL e cabeçalho corretos. Chamadas sem autenticação ou com autenticação inválida receberam 401 pelo domínio público. Pareamento concluído: Evolution confirmou estado `open` e o Antares recebeu callback autenticado pelo webhook público. Nenhuma mensagem de teste foi enviada.

Aba Disparos adicionada à Caixa de entrada, exclusiva para administradores/proprietários, reunindo criação de disparos, escolha de contatos/modelos, processamento da fila e estado dos canais. Publicada após build e verificação de tipos aprovados; bundle conferido no domínio público. Backend, worker e conexão Evolution mantidos em execução durante esta promoção do frontend.

Seletor de conta movido da sidebar para Contas de clientes. A página permanece acessível a quem pode alternar contas, inclusive dentro de uma conta de cliente, permitindo retornar à conta principal; gestão de contas/equipe mantém as permissões anteriores. Build e tipos aprovados; atualização do frontend publicada e bundles conferidos no domínio público.

Operação movida para uma aba em Configurações e removida da sidebar. Indicadores, filas, backup e preferências de contato preservados, com acesso restrito a administradores/proprietários. `/operacao` redireciona para `/configuracoes?tab=operacao`. Build e tipos aprovados; frontend publicado, bundle e redirecionamento Next.js conferidos no domínio público.

## Revisão de textos e área útil — 21/10/2026

As 12 páginas de trabalho foram revisadas: visão geral, contatos, empresas, funil, caixa de entrada, tarefas, atividades, formulários, automações, relatórios, contas de clientes e configurações. Removidos subtítulos de apresentação, slogans, banners explicativos repetidos e instruções óbvias em estados vazios. Cabeçalhos internos mantêm título e ações. Importação/exportação de contatos e empresas agora ficam no cabeçalho, liberando uma linha. Operação usa a barra de abas de Configurações para atualizar o estado, sem outro cabeçalho repetido.

Reduzidas margens e espaçamentos, cabeçalhos e preenchimento dos cartões; retirada a largura máxima fixa do conteúdo. Fontes das tabelas e tamanhos de botões preservados. Mantidos dados cadastrados, descrições públicas dos formulários/agendas, consentimentos, mensagens de erro e confirmações de exclusão, senha, bloqueio ou cancelamento. Instruções de conexão e regras de automações preservadas quando necessárias.

Validação em banco descartável: todas as 12 páginas em 1440px e 390px sem transbordamento horizontal do documento, incluindo conferência posterior de Disparos, Operação e Links de agendamento. Corrigida quebra dos controles do funil no celular. Console sem erros/avisos na conferência final. Capturas: `output/playwright/compact-contatos-desktop.png` e `output/playwright/compact-mensagens-mobile.png`. Na lista de demonstração a 1440×900, o cabeçalho ocupa 40px e a tabela exibe 9 registros por página. Banco e servidores de revisão removidos ao terminar.
