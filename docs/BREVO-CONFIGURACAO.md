# Brevo: acesso ao sistema e campanhas

## Conectar uma conta

Em **Configurações → Conexões → Brevo**, informe uma chave de API do Brevo, o nome e o e-mail de um remetente ativo.
O servidor valida a chave consultando a conta e os remetentes. A chave é cifrada antes de ser salva e nunca é devolvida pela API.
A conexão pertence ao workspace selecionado; campanhas de outro cliente não herdam suas credenciais.
Use contas Brevo distintas para clientes que precisem de bases e bloqueios totalmente independentes.

Depois de conectar, use **Ativar acompanhamento**. O Antares configura um webhook de marketing em
`APP_URL/api/v1/brevo/webhook/CONNECTION_ID`, autenticado pelo cabeçalho privado `X-Brevo-Secret`.
Entregas, aberturas, cliques, falhas, reclamações e descadastros atualizam os resultados da campanha.
Descadastros, reclamações e falhas permanentes bloqueiam também os contatos locais com o mesmo endereço.

A autenticação do domínio deve ser concluída no Brevo. Um remetente ativo não comprova, por si só, a autenticação DNS do domínio.

Erros de chave, permissão ou IP autorizado aparecem como falhas de validação (HTTP 422), com orientação específica.
Não use a chave SMTP no campo de API. Espaços no início/fim da chave são removidos; espaços internos e quebras de linha são rejeitados.
O corpo bruto de erros do provedor e as credenciais não são registrados nos logs. A resposta HTTP 502 não é usada para uma chave recusada,
pois o proxy público pode substituir a resposta JSON por uma página HTML e ocultar a orientação da tela.

## Recuperação e convites

**Esqueci minha senha** solicita conta e e-mail. A resposta é idêntica para contas existentes, inexistentes ou sem envio disponível.
O link dura 30 minutos. **Configurações → Equipe → Convidar por e-mail** cria um usuário inativo e envia um link com validade de 24 horas.
O usuário define a própria senha e só então é ativado. Para reenviar um convite pendente, informe o mesmo e-mail.
Existe intervalo mínimo de 60 segundos entre links para o mesmo usuário.

Somente o hash do token é persistido. O token vai no fragmento da URL, é removido do endereço ao abrir a página e só é enviado
ao endpoint de confirmação. O link é de uso único, valida a conta e a versão do acesso e encerra as sessões anteriores ao mudar a senha.
Envios ambíguos ficam sem confirmação; nunca há reenvio automático.

Por padrão, os e-mails de acesso usam a conexão Brevo da conta de origem do usuário. Opcionalmente, o administrador do servidor
pode configurar um remetente central exclusivo para acesso com `BREVO_SYSTEM_API_KEY`, `BREVO_SYSTEM_SENDER_EMAIL` e
`BREVO_SYSTEM_SENDER_NAME`. Essa configuração não habilita campanhas em contas de clientes.

`BREVO_ENCRYPTION_KEY` aceita uma chave Fernet. Sem ela, a cifra deriva de `SECRET_KEY` com contexto exclusivo para o Brevo.
Preserve a configuração privada e a chave em backup; mudar a chave impede a leitura das credenciais já cifradas.
`APP_URL` deve ser a URL canônica pública do Antares. Em desenvolvimento, use a URL e as credenciais isoladas do ambiente.

## Campanhas

O menu **Campanhas** está disponível para administradores e proprietários. Crie ou edite um rascunho com nome, assunto,
mensagem de texto e filtros opcionais de tag/origem. A prévia exclui contatos arquivados, sem e-mail, inválidos, duplicados e bloqueados.
O filtro **Com e-mail** é dinâmico; não cria uma tag nem representa autorização de marketing.
As tags já existentes continuam editáveis no cadastro/importação e agora aparecem na lista e nos filtros de contatos.

1. Revise a mensagem e o público (até 1.000 e-mails por campanha).
2. Use **Preparar no Brevo** para criar uma lista exclusiva e iniciar a importação, sem enviar mensagens.
3. Use **Consultar Brevo** até a importação terminar e o rascunho remoto ficar pronto.
4. Use **Revisar e enviar**, confirme a autorização do público e confirme o envio.

Campanhas usam a API de marketing (`emailCampaigns`), com link de descadastro; links de acesso usam a API transacional (`smtp/email`).
Não são enviados convites ou campanhas reais durante os testes automatizados.
A importação não altera os contatos existentes nem remove bloqueios do Brevo. A associação à lista é feita depois da importação.
O público é conferido novamente antes de enviar. Se ele mudou, crie um novo rascunho.

Preparação e envio têm uma confirmação persistida antes de operações externas. Timeout ou retorno ambíguo bloqueia nova tentativa automática;
confira o painel Brevo. A consulta de uma campanha com envio ambíguo nunca a torna enviável novamente automaticamente.
Trocar a chave invalida o vínculo de rascunhos preparados anteriormente. Não altere a conexão enquanto houver preparação/importação/envio em andamento.

## Referências

- https://developers.brevo.com/docs/send-a-transactional-email
- https://developers.brevo.com/reference/create-email-campaign
- https://developers.brevo.com/reference/import-contacts
- https://developers.brevo.com/docs/marketing-webhooks

## Campanhas e modelos por canal

A página **Campanhas** reúne campanhas e modelos de e-mail e WhatsApp. A Caixa de
entrada permanece dedicada às conversas. Os modelos existentes são preservados,
inclusive os usados em automações. Ao escolher um modelo, o assunto e a mensagem
são copiados para o rascunho; editar a campanha não altera o modelo original.

E-mail usa campanhas nativas do Brevo (até 1.000 destinatários). WhatsApp usa a
conexão da conta e a fila persistente do Antares (até 100 destinatários). Ambos
permitem segmentar por tag e origem, revisar o público e confirmar o consentimento
antes de enviar. Telefones duplicados, inválidos, contatos arquivados e bloqueados
são excluídos do público do WhatsApp.

Após confirmar uma campanha de WhatsApp, mantenha a página aberta para processar
os destinatários. É possível pausar após a mensagem atual e retomar por
**Continuar envio**. Cada requisição processa somente uma mensagem dessa campanha;
a fila de outras campanhas e atendimentos não é processada por esse botão. O
worker global mantém sua configuração atual. Resultados sem confirmação não são
reenviados automaticamente. Permissão do responsável, telefone e bloqueios são
verificados novamente antes de cada envio.
