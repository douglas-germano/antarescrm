# Pesca — Copiloto com OpenRouter

A primeira fase da proposta está implementada: link + legenda + imagem opcional → triagem → rascunhos → revisão → copiar e abrir Instagram → confirmação humana → métricas. Não há coleta automática nem publicação pela API nesta fase.

## Configuração do servidor

Backend e worker precisam das mesmas variáveis, fornecidas pelo ambiente privado de execução:

```dotenv
OPENROUTER_API_KEY=<chave privada da plataforma>
FISHING_TRIAGE_MODEL=<identificador OpenRouter do modelo de triagem>
FISHING_DRAFT_MODEL=<identificador OpenRouter do modelo de rascunho>
```

Não há modelos fixos nem geração habilitada por padrão. Escolha modelos que suportem `response_format: json_schema`, e visão se usar imagens. Os nomes de modelos apresentados na proposta eram exemplos; não são assumidos como IDs disponíveis no provedor. A chave nunca vai para o navegador nem é armazenada nas tabelas da Pesca.

`FISHING_ALLOW_FREE_MODEL_TRAINING=true` permite roteamento com coleta de dados somente para modelos com ID terminado em `:free`. O padrão é `false`; modelos pagos continuam com `data_collection=deny`. Habilite apenas após autorizar a política do provedor para os dados enviados. A conta e a chave do OpenRouter também precisam permitir o uso desses endpoints.

`FISHING_DISABLE_REASONING=true` envia `reasoning.enabled=false`. Use somente com modelos compatíveis que permitam desativar o raciocínio, como o Nemotron selecionado para o teste. Isso preserva o limite de saída para o JSON dos comentários. O padrão é `false`.

Referências do contrato: [saída estruturada](https://openrouter.ai/docs/guides/features/structured-outputs), [uso e custo](https://openrouter.ai/docs/cookbook/administration/usage-accounting). O adaptador usa Chat Completions, exige suporte aos parâmetros e pede provedores com `data_collection=deny`; a disponibilidade depende do modelo e da conta do provedor. As políticas externas de retenção continuam sendo as do OpenRouter e do provedor selecionado.

Aplique a migração pelo procedimento habitual, com backup anterior:

```bash
cd backend
.venv/bin/flask --app run db upgrade
```

Reinicie backend e worker depois de configurar o ambiente. Em Docker, ambos recebem `backend.env` pelo compose existente. O worker atual `run-worker --no-dispatch` também processa os posts habilitados da Pesca. A opção `--no-dispatch` continua controlando o envio de mensagens, não o processamento de IA autorizado pela configuração da Pesca.

Não aplique mudanças diretamente ao banco de produção para testar. Os testes usam bancos descartáveis e provedores falsos.

## Uso na conta

1. Administrador: Configurações → Pesca. Preencha perfil, tom, exemplos, assuntos, palavras proibidas, próprio perfil e objetivo.
2. Ajuste os limites e marque a autorização de processamento pela IA. Salve.
3. Pesca → Fontes. Cole a URL HTTPS de um post/reel do Instagram e a legenda. Opcionalmente informe o autor e anexe PNG, JPEG ou WebP de até 4 MiB.
4. O worker avalia e, acima da nota mínima, solicita três estilos de comentário. Opções inválidas são eliminadas; podem sobrar menos de três na fila.
5. Revise, escolha, edite e clique em **Copiar e abrir post**. A área de transferência precisa estar permitida. Cole e publique manualmente no Instagram.
6. Volte ao Antares e confirme **Sim, publiquei** ou **Não publiquei · pular**. Apenas quem abriu o card pode confirmar. Uma aba bloqueada pelo navegador pode ser reaberta pelo link do card pendente.

Não se presume publicação só porque o Instagram foi aberto. Desfazer uma confirmação altera apenas o registro no Antares; não apaga comentários do Instagram.

## Limites e falhas

- Padrões por conta: 40 comentários/dia, 100 chamadas de IA/dia, corte 60/100 e até 200 cards ativos. Dia calculado no fuso da conta.
- Aberturas pendentes reservam espaço no limite diário e bloqueiam outro comentário no mesmo autor. Um comentário confirmado bloqueia o autor por sete dias. Sem autor informado, essa regra não pode ser aplicada.
- Cinco publicações nos últimos dez minutos geram aviso na próxima abertura.
- Cards ativos expiram 48 horas depois de adicionados; a idade real do post depende da seleção feita pela pessoa. O MVP não busca a data no Instagram.
- Imagens são apagadas do registro ao decidir ou após 48 horas, inclusive para posts descartados ou com falha. Legendas, rascunhos e registros operacionais permanecem no histórico da conta e nos backups conforme a política geral de retenção.
- O JSON é validado no backend; links, menções, hashtags, preço, termos proibidos e textos muito parecidos com os últimos 50 comentários são recusados. As verificações também se aplicam ao texto editado antes de abrir o post.
- Cada avaliação usa uma chamada; posts aprovados usam outra para rascunho. “Gerar outras” repete a avaliação e preserva o histórico das gerações.
- Chamadas são reservadas no banco antes do envio para respeitar o limite, inclusive se falharem. Não há repetição automática de chamadas. Limite de saída: 1.200 tokens; timeout de conexão de 3 s e de leitura de 20 s por chamada.
- Falhas ficam visíveis no filtro **Falhas**. Processamentos interrompidos há mais de cinco minutos são marcados com erro; a pessoa decide se quer gerar novamente, porque o custo da tentativa pode ser desconhecido.
- O custo exibido é a soma dos valores devolvidos pelo provedor, em dólares. Chamadas sem custo informado são contadas separadamente. Não há conversão para reais, cobrança ou repasse automático.
- Conteúdo enviado à IA: perfil da marca, legenda, autor informado, imagem opcional e últimos dez comentários da Pesca. Não inclui o CRM ou a caixa de entrada. O modelo não recebe ferramentas, credenciais nem acesso ao link.

## O que ainda pertence às próximas fases

Menções, migração para Unified Login, descoberta de perfis, hashtags, coleta programada, quadros de vídeo, atribuição de DMs e contatos, Insights, relatórios por período/usuário e métricas de funil. A seção Fontes mostra essa limitação; não simula fontes automáticas conectadas.

As métricas atuais são acumuladas: status dos posts, confirmações de publicação, aproveitamento (publicados / posts que entraram na fila), taxa de edição, tokens, custo informado e limites do dia. São registros operacionais, não confirmação de alcance ou de publicação pela Meta.
