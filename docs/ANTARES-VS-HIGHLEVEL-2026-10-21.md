# Antares: lacunas em relação ao HighLevel

Data: 21/10/2026. Escopo: código deste checkout, configuração local consultada sem expor segredos e documentação pública dos fornecedores. Esta é uma avaliação de produto e arquitetura; não foi realizada uma nova bateria completa de testes nem validação de entrega por provedores nesta análise. Nenhuma funcionalidade foi instalada ou publicada.

## Diagnóstico

O Antares tem uma base de CRM para agência, com isolamento de contas, contatos, empresas, oportunidades, atividades, tarefas e acompanhamento comercial. Ainda faltam profundidade nas automações e módulos completos de captação, agendamento, comunicação, faturamento e distribuição do produto.

A página oficial do HighLevel apresenta CRM, automações, páginas/funis, agendamento, comunicação, pagamentos, reputação e recursos de IA. A comparação abaixo usa essas famílias como referência; não representa auditoria exaustiva de todos os planos do fornecedor.

Fonte: [HighLevel](https://www.gohighlevel.com/) e [API oficial](https://marketplace.gohighlevel.com/docs/).

## Matriz de lacunas

| Área | Evidência no Antares | Trabalho necessário | Prioridade proposta |
|---|---|---|---|
| Operação contínua | Backend/frontend/túnel ativos; nenhum processo run-worker encontrado | Worker supervisionado, monitoramento da fila, alertas, backup automático com restauração testada e hospedagem independente do Mac | P0 |
| Comunicação | SMTP, Twilio e Evolution implementados; COMMUNICATION_ACCOUNTS vazio, Evolution sem URL/chave e WhatsApp desconectado | Configuração por conta, conexão de provedores, entrada real de mensagens, estados de entrega e testes de ponta a ponta | P0 |
| CRM | Contatos, empresas, tags, campos JSON, histórico, importação/exportação e um conjunto de etapas por workspace | Entidade de múltiplos funis, campos tipados configuráveis, listas dinâmicas persistidas no servidor e distribuição de leads | P1 |
| Automações | Apenas contact.created e form.submitted; ações create_task, send_message e follow_up; filtros por origem/tag e atrasos | Gatilhos de resposta, mudança de etapa, agendamento e pagamento; condições AND/OR; ramificações; espera por evento/timeout; parar ao receber resposta; versões publicadas e execução de teste | P1 |
| Formulários | Campos públicos fixos de nome, e-mail e telefone; consentimento; cria contato/negócio | Construtor de campos tipados, mapeamento para CRM, respostas armazenadas por envio, lógica condicional, incorporação, personalização por conta e captura de UTMs | P1 |
| Agendamento | Calendário de tarefas e atividades, sem modelos/rotas de reservas públicas | Disponibilidade, duração, intervalos, prevenção de conflitos, distribuição entre atendentes, cancelamento/reagendamento, lembretes e sincronização de calendários | P1 |
| Atendimento | Caixa unificada para modelos internos de email/SMS e conversas WhatsApp; atribuição existe no WhatsApp | Instagram/Messenger/chat do site, notificações em tempo real, filas de equipe e consolidação de identidade multicanal | P1/P2 |
| Campanhas | Templates de texto e disparos de até 100 contatos por requisição | Segmentação persistente, editor de email, programação, eventos de entrega/rejeição, descadastro/supressão por canal e personalização além de nome/email/telefone | P1/P2 |
| Sites e funis | Não encontrados modelos/rotas/editor/publicação de páginas de marketing | Editor, blocos, assets, versões, domínios, etapas do funil, publicação e métricas | P2 |
| Cobrança | Não encontrados modelos de pagamentos, faturas ou assinaturas | Produtos, propostas, checkout, cobrança recorrente, webhooks idempotentes e conciliação | P2 |
| Agência/SaaS | Contas-filhas, troca de conta, suspensão e concessão de acesso | Marca/domínio por conta, planos, limites, consumo, cobrança, provisionamento e pacotes reutilizáveis de configurações | P2 |
| Integrações | API interna e webhooks de provedores | API pública documentada, credenciais com escopos por conta e eventos de saída com assinatura e reenvio controlado | P1/P2 |
| Relatórios | Resumo comercial, vendas por responsável, perdas e atividades | Atribuição de campanhas, conversão por etapa, tempo de resposta, faltas, receita recebida e consumo por conta | P2 |
| IA e complementos | Não encontrados serviços/modelos de IA, telefonia, reputação, social planner ou cursos/comunidades | Atendimento com encaminhamento humano, conhecimento por conta e auditoria; demais módulos conforme oferta comercial | P3 |

P0 = tornar a base atual operacional; P1 = fechar o percurso comercial; P2 = ampliar plataforma e venda SaaS; P3 = extensões após validar o núcleo. Prioridade é recomendação, não compromisso de prazo.

## Evidências locais

- `backend/app/models.py`: Workspace, WorkspaceAccess, Contact, Company, PipelineStage, Opportunity, LeadForm, FormSubmission, AutomationRule, AutomationRun, AutomationJob, InboxThread e InboxMessage. PipelineStage não possui pipeline_id; não há entidade Pipeline.
- `backend/app/routes/growth.py`: esquemas de formulário, enumeração de gatilhos e ações e captura pública.
- `backend/app/services/automations.py`: agendamento persistente, execução sequencial e filtros disponíveis.
- `backend/app/services/communications.py`: adaptadores SMTP/Twilio/WhatsApp; variáveis de template name/email/phone.
- `frontend/src/app/(app)/agenda/page.tsx` e `/api/v1/calendar`: agenda operacional, sem reserva pública.
- `frontend/src/app/(app)/formularios/page.tsx` e `frontend/src/app/f/[formId]/page.tsx`: configuração e página pública com campos fixos.
- `backend/app/access.py` e `backend/app/routes/agency.py`: permissões e contas de clientes.
- Problema já identificado que segue pendente: `reports/won-by-month` compara closed_at com um objeto date; a falha de conversão foi registrada no log. Corrigir antes de tratar relatórios como validados integralmente.
- Git continua sem commit inicial. O README ainda descreve permissões antigas. Versionamento e documentação precisam acompanhar a evolução.

## Pesquisa com find-reverse-engineered

Executados search para highlevel, gohighlevel, calendly, mautic, whatsapp e instagram. Não houve correspondência para HighLevel/GoHighLevel no índice consultado; isso não prova inexistência de projetos fora dele.

O HighLevel tem API oficial com OAuth/tokens, CRM, conversas, agenda, pagamentos e webhooks. Ela serve para integrar uma conta HighLevel existente, não para obter seu código ou substituir a construção do Antares.

Projetos localizados:

- [whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js): escolhido como referência técnica de cliente não oficial, por implementar comunicação via WhatsApp Web. Versão 1.34.7 no package.json consultado; Apache-2.0. README e metadados lidos pela web. O índice registrava atividade em outubro de 2026. O clone e as consultas diretas ao GitHub pelo terminal não concluíram por indisponibilidade de rede; não há commit local validado, instalação ou código executado.
- [GOWA](https://github.com/aldinokemal/go-whatsapp-web-multidevice): alternativa REST em Go, multi-conta e webhooks; MIT segundo o repositório. README consultado pela web. Candidato complementar; versão/commit não fixados nesta avaliação.
- Clientes privados de Instagram apareceram, mas não foram selecionados: o caminho proposto para atendimento empresarial é a integração oficial aplicável à conta.

A recomendação de produto é implementar o adaptador da [WhatsApp Cloud API oficial](https://www.postman.com/meta/whatsapp-business-platform/overview), mantendo uma fronteira de provedores. O adaptador Evolution atual pode ser preservado. Trocar Evolution por outra biblioteca não entrega os recursos que faltam ao CRM. Clientes não oficiais podem quebrar e o próprio whatsapp-web.js alerta para bloqueio de conta. Nenhuma credencial foi usada nesta pesquisa.

Componentes adicionais, pesquisados fora do índice de engenharia reversa:

- [React Flow](https://reactflow.dev/), núcleo MIT: candidato para o editor visual. É interface de nós e conexões; o motor de execução, versões e eventos continuam sendo responsabilidade do Antares. Exemplos e ofertas Pro devem ser avaliados separadamente.
- [GrapesJS](https://github.com/GrapesJS/grapesjs), núcleo BSD-3-Clause: candidato ao construtor de páginas. Não fornece sozinho domínios, publicação, métricas ou isolamento de clientes. Não confundir o núcleo com produtos comerciais e plugins.

Esses dois componentes são candidatos de arquitetura, não dependências instaladas ou versões homologadas.

## Ordem recomendada e critérios de aceite

1. Operar o que já existe: worker supervisionado, configuração dos canais, teste com destinatários autorizados, alertas e tratamento de descadastro/supressão antes de campanhas. Aceite: lead recebido gera a ação, a fila processa sem intervenção e a mensagem tem estado verificável sem duplicação.
2. Formulários configuráveis e agendamento público. Aceite: captura grava respostas, atualiza os campos mapeados e permite reservar/reagendar sem conflito.
3. Motor de eventos e automações condicionais. Aceite: uma resposta recebida cancela o retorno automático pendente; ramificações e timeouts são testáveis e auditáveis. Construir o motor antes ou em conjunto com o editor visual.
4. Páginas/funis, integração de canais adicionais e métricas. Aceite: página publicada em domínio configurado, origem atribuída ao lead e conversão acompanhada até o negócio.
5. Pagamentos, marca por conta e pacotes de configuração. Aceite: provisionar um cliente com um pacote selecionado e aplicar corretamente plano, permissões e limites.
6. IA, reputação, social planner, telefonia e conteúdo conforme os usos que os clientes validarem.

Uma primeira meta comercial recomendada é demonstrar: página → formulário → contato → atendimento → reserva → negócio → pagamento. Hoje o sistema cobre partes desse caminho; ainda não o percurso completo.

## Referências específicas

- [Formulários condicionais](https://help.gohighlevel.com/support/solutions/articles/155000001314-conditional-logic-v2-in-forms-and-surveys-)
- [If/Else em workflows](https://help.gohighlevel.com/support/solutions/articles/155000002471)
- [Snapshots](https://help.gohighlevel.com/support/solutions/articles/48000982513-how-to-share-snapshots)
- [SaaS Mode](https://www.gohighlevel.com/saas-mode)
- [Agenda e reservas pela API](https://marketplace.gohighlevel.com/docs/ghl/calendars/calendar-events/)
- [Versão consultada do whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js/blob/main/package.json)
- [Licença React Flow/xyflow](https://github.com/xyflow/xyflow/blob/main/LICENSE)
