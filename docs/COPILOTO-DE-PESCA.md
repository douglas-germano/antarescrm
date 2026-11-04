# Copiloto de pesca — especificação

Status: fase 1 (MVP com links colados) implementada no código em 03/11/2026; ativação depende de migração e configuração do OpenRouter. As demais fases continuam planejadas. Operação e limites: [PESCA-OPERACAO.md](PESCA-OPERACAO.md). Proposta original: 28/10/2026.

## Objetivo

Ajudar o cliente a comentar, com qualidade e em volume, nos posts onde o seu público já está (perfis de
referência, concorrentes, hashtags do nicho), para atrair visitas ao perfil, seguidores e DMs. Quando esse
público responde, a Caixa de entrada e as automações que já existem assumem.

A IA encontra, lê, filtra e rascunha. **A pessoa publica.** O Antares nunca publica comentário em post de terceiros.

## Limites da plataforma (decisões que moldam o desenho)

Conferido na documentação da Meta em 28/10/2026 (exemplos da documentação em v26.0; o Antares usa v25.0).

**Comentar em post de terceiros.** A única escrita documentada em mídia de outra conta é a resposta a menção
(`POST /{ig-user-id}/mentions`). A documentação diz expressamente que não é possível comentar em mídia
encontrada pela busca por hashtag nem em fotos onde a conta foi marcada (tag). Os próprios posts já são tratados
em `services/instagram.py` (`process_comment`). Robô de navegador ou API não oficial ficam fora de escopo:
violam os termos do Instagram e colocam em risco a conta do cliente e a aprovação do app na Meta.

**Tipo de conexão.** A Meta tem três formas de integração:

| Recurso | Instagram Login (atual) | Facebook Login | Unified Login |
|---------|-------------------------|----------------|---------------|
| Hashtag Search | não | sim | sim |
| Business Discovery | não documentado | sim | sim |
| Menções (ler e responder) | sim | sim | sim |
| Host | `graph.instagram.com` | `graph.facebook.com` | `graph.facebook.com` |
| Exige Página do Facebook | não | sim | não (exige portfólio empresarial) |

A Meta recomenda o **Unified Login** para integrações novas e diz que novos recursos saem só nele. O token é de
usuário do sistema da integração (continua valendo se a pessoa que conectou sair da empresa). Existe guia de
migração a partir do Instagram Login (`instagram-api-with-unified-login/migration`), ainda não lido: falta
saber se a conexão atual é aproveitada ou se o cliente precisa conectar de novo.

Atenção: as páginas de referência de `recent_media` e `top_media` ainda dizem "disponível com Facebook Login",
enquanto a página do recurso e a visão geral incluem o Unified Login. Testar antes de assumir.

**Decisão:** migrar a conexão do Instagram para Unified Login, porque destrava a coleta automática sem
exigir Página do Facebook e é onde a Meta vai lançar novidades. Até lá, o copiloto funciona com links colados
(fonte 3) e com menções (fonte 4), que já são suportadas pela conexão atual.

**Permissões e revisão.**
- Hashtag Search: permissão `instagram_basic` e recurso *Instagram Public Content Access*, ambos com App Review.
  Se o papel na Página veio do Business Manager, também `pages_read_engagement` (ou `ads_management`/`business_management`).
- Business Discovery: `instagram_basic`, `instagram_manage_insights` e `pages_read_engagement`
  (mais `ads_management` ou `ads_read` no mesmo caso do Business Manager).
- Responder menção: `instagram_basic`, `instagram_manage_comments` e `pages_read_engagement`; para responder
  menção feita em comentário, também `pages_show_list`.
- Atender contas que não são da Advantage Midia exige **Advanced Access**, que pede App Review e
  **verificação da empresa**.

**Limites da busca por hashtag.**
- 30 hashtags distintas por conta numa janela móvel de 7 dias. Repetir a mesma hashtag não conta de novo nem
  reinicia o prazo; cada chamada a `recent_media` ou `top_media` conta para o limite.
- `recent_media` devolve só posts publicados nas últimas 24 h; `top_media` usa o mesmo critério de popularidade
  do Instagram. Até 50 por página, só públicos, sem anúncios, sem ordem cronológica garantida, sem Stories,
  sem emoji na busca. Hashtags sensíveis devolvem erro genérico.
- Campos: `caption`, `children`, `comments_count`, `id`, `like_count` (some se o dono ocultou curtidas),
  `media_type`, `media_url` (não vem em álbum e falta em alguns reels), `permalink`, `timestamp`.
  **Não é possível pedir o `username`**: o autor do post é desconhecido.

**Limites do Business Discovery.**
- Chamada: `GET /{ig-user-id-da-conta-conectada}?fields=business_discovery.username(@alvo){...}`.
- Só lê contas comerciais ou de criador; contas com restrição de idade não retornam.
- Os campos da mídia precisam vir na própria chamada (expansão do campo `media`): um `GET` direto na mídia
  retornada falha por falta de permissão. A referência mostra `id`, `comments_count`, `like_count` e
  `view_count`; `caption`, `permalink`, `media_url` e `timestamp` não estão confirmados nessa página e
  precisam ser testados. Paginação com cursores `before`/`after`.

**Limites das menções.**
- Webhook `mentions`. Leitura por `mentioned_media` (menção na legenda) e `mentioned_comment` (menção em comentário).
- Resposta via `POST /{ig-user-id}/mentions` com `media_id` e `message` (e `comment_id`, se a menção foi em
  comentário). A resposta aparece como comentário em sequência.
- Sem menções em Stories, sem webhook de contas privadas, sem comentário em fotos onde a conta foi só marcada.

## Fontes

| # | Fonte | Como coleta | O que traz | Observações |
|---|-------|-------------|------------|-------------|
| # | Fonte | Conexão | Como coleta | O que traz | Observações |
|---|-------|---------|-------------|------------|-------------|
| 1 | Perfis-alvo | Unified Login | Business Discovery, a cada 2 h | Posts recentes com métricas; legenda e link a confirmar | Só contas comerciais ou de criador. Até 50 perfis por workspace. Autor conhecido. |
| 2 | Hashtags | Unified Login | `recent_media` a cada 2 h; `top_media` 1 vez por dia | Legenda, mídia, link, data, curtidas, comentários | **Autor desconhecido.** Até 10 hashtags ativas, para sobrar cota na janela de 7 dias. |
| 3 | Link colado | nenhuma | O usuário cola a URL e a legenda (e pode anexar a imagem) | O que a pessoa colar | Funciona com a conexão atual. Base do MVP. |
| 4 | Menções | atual | Webhook `mentions` | Post ou comentário onde a marca foi @citada | Único caso em que o Antares pode comentar sozinho, após clique de aprovação. |

Regras de coleta: ignorar posts com mais de 72 h (comentário cedo rende mais; `recent_media` já se limita a
24 h), posts já vistos (chave `media_id`) e posts da própria conta. A API não lista comentários de posts de
terceiros. Como a busca por hashtag não traz o autor, o link do post (`permalink`) é a única forma de abrir o
post e as regras por autor não valem para essa fonte.

## Fluxo

1. **Coleta** (worker, `run-worker`): busca nas fontes e grava `fishing_posts` com status `novo`.
2. **Triagem** (modelo rápido): nota de 0 a 100 e motivo. Abaixo do corte do workspace (padrão 60) vai para
   `descartado`; o usuário pode ver e recuperar.
3. **Rascunho** (modelo principal, com visão): 3 opções de comentário para os aprovados na triagem → `na_fila`.
4. **Fila**: o usuário revisa, edita, escolhe e toca em **Comentar**. O Antares copia o texto e abre o post.
5. **Confirmação**: ao voltar para a aba, o card pergunta *Publicou?* (padrão sim, com desfazer) → `publicado`
   ou `pulado`.
6. **Retorno**: DMs e contatos novos que caírem na janela de atribuição recebem origem `pesca` (ver Métricas).

Expiração: card não decidido em 48 h vira `expirado`.

## Prompt da IA

Duas chamadas, para manter custo baixo: triagem em lote com modelo rápido (`claude-haiku-5-5`) e rascunho por
post com o modelo principal (`claude-sonnet-5-5`), recebendo a imagem (ou a capa e até 3 quadros do vídeo).
Saída sempre em JSON validado no backend; resposta fora do formato descarta o rascunho sem tentar de novo.

### Perfil da marca (configurado pelo cliente, entra nas duas chamadas)

- O que a marca faz e para quem (2 a 3 frases)
- Tom de voz: 3 adjetivos e 2 exemplos de comentário que a marca faria
- Assuntos que pode e não pode tocar
- Palavras proibidas
- Objetivo da pesca: seguidores, visitas ao perfil ou DMs

### Triagem — sistema

```text
Você avalia posts do Instagram para uma marca decidir onde vale comentar.
Marca: {perfil_da_marca}

Dê nota de 0 a 100 para cada post, considerando:
- o público do post é o público da marca;
- existe algo concreto para comentar (uma ideia, uma dúvida, um resultado, uma opinião);
- comentar ali é natural, sem parecer propaganda.

Nota 0 obrigatória para: luto, doença, tragédia, política, religião, polêmica, conteúdo de menor de idade,
sorteio, post de concorrente direto vendendo, e qualquer post em que um comentário de marca seria inoportuno.

Responda só com JSON: {"posts":[{"id":"...","nota":0,"motivo":"até 15 palavras"}]}
```

### Rascunho — sistema

```text
Você escreve comentários no Instagram em nome de {nome_da_marca}, como uma pessoa real da equipe faria.
Marca: {perfil_da_marca}

Antes de escrever, entenda o post: o assunto, o que o autor quis dizer, o que a imagem mostra.
Escreva 3 opções diferentes entre si:
1. uma que acrescenta algo (uma dica, um dado, uma experiência);
2. uma que faz uma pergunta genuína ao autor;
3. uma de reação específica, curta.

Regras:
- Português do Brasil, natural, de 1 a 2 frases, no máximo 220 caracteres.
- Precisa citar algo específico deste post. Se o comentário servisse em qualquer outro post, reescreva.
- Sem links, sem @, sem hashtags, sem preço, sem "chama no direct", sem falar da própria marca ou produto.
- No máximo 1 emoji, e só se combinar com o tom.
- Nada de elogio vazio ("que post incrível", "amei", "conteúdo top").
- Não invente fatos sobre o autor nem sobre a marca.
- Se não houver comentário bom e honesto para este post, devolva "pular": true.

Responda só com JSON:
{"pular":false,"resumo_do_post":"1 frase","opcoes":[{"tipo":"acrescenta|pergunta|reacao","texto":"..."}]}
```

### Rascunho — usuário

```text
Fonte: {perfil @autor | hashtag #tag | link}
Data: {data}  Curtidas: {n}  Comentários: {n}
Legenda:
"""{legenda}"""
[imagem ou quadros anexados]
Últimos comentários publicados pela marca (para não repetir): {ultimos_10_textos}
```

### Verificações no backend, depois da IA

- Tamanho, ausência de link, @, hashtag e palavras proibidas.
- Similaridade alta com os últimos 50 comentários publicados → descarta a opção.
- Nenhuma opção válida → card não entra na fila.

## Fila de aprovação

**Card:** miniatura do post, autor ou hashtag de origem, idade do post, nota e motivo da triagem, resumo do post
e as 3 opções (a primeira já selecionada). O texto escolhido é editável no próprio card.

**Ações:** Comentar · Gerar outras · Pular · Não mostrar este perfil/hashtag. Atalhos de teclado no desktop:
`1` `2` `3` escolhem, `E` edita, `Enter` comenta, `P` pula.

**Comentar:** copia o texto para a área de transferência e abre a URL do post (no celular, o app do Instagram).
Registra `aberto_em`. A confirmação acontece no retorno, como descrito no Fluxo.

**Guardas contra spam** (configuráveis, com padrões conservadores):
- até 40 comentários publicados por dia por workspace; ao atingir, a fila pausa até o dia seguinte;
- no máximo 1 comentário por autor a cada 7 dias (fontes 1, 3 e 4; na fonte 2 o autor é desconhecido);
- aviso se forem publicados mais de 5 em 10 minutos;
- edição mínima não é exigida, mas a métrica *taxa de edição* aparece para o gestor.

**Ordenação:** nota da triagem, com bônus para posts mais novos e com menos comentários (mais visibilidade).

**Menções (fonte 4):** card igual, com o botão **Comentar pelo Antares**, que publica via API após o clique.

## Telas

Nova entrada no menu: **Pesca** (`/pesca`), com três abas. Seguir o padrão visual atual (estilo Gaio), mobile
primeiro na fila, porque a publicação acontece no celular.

1. **Fila** — os cards, um contador do dia ("12 de 40"), filtro por fonte. Estado vazio explica o próximo passo
   (cadastrar fontes ou aguardar a próxima coleta, com horário).
2. **Fontes** — lista de perfis e hashtags com liga/desliga, última coleta, posts encontrados e taxa de
   aprovação por fonte; campo para colar link de post; aviso de cota de hashtags na janela de 7 dias.
3. **Resultados** — as métricas abaixo, por período.

Em **Configurações → Pesca**: perfil da marca, exemplos de comentários, palavras proibidas, nota de corte,
limites diários e janela de atribuição. Em **Configurações → Conexões**: reconectar pelo Unified Login, com
aviso de quais fontes ficam liberadas depois disso.

## Métricas

Operação (exatas, vêm do próprio Antares):
- posts coletados, descartados na triagem, na fila, publicados, pulados, expirados;
- taxa de aproveitamento (publicados ÷ enviados para a fila) e taxa de edição;
- tempo médio por card e comentários por dia, por usuário;
- desempenho por fonte (aproveitamento e retorno), para cortar fontes ruins.

Resultado (aproximadas — a API não liga uma visita ou seguidor a um comentário):
- **Perfil da conta por dia:** visitas ao perfil e novos seguidores (Insights da própria conta), em gráfico
  junto com comentários publicados por dia;
- **Contatos com origem `pesca`:** DM ou contato novo cujo @ é o autor de um post comentado nos últimos 7 dias
  (atribuição forte; só para fontes com autor conhecido), ou marcação manual na Caixa de entrada (atribuição informada);
- **Funil:** contatos `pesca` → negócios → ganhos, usando o CRM existente.

Na tela, separar números exatos dos aproximados, com a explicação de como cada um é calculado.

Custo de IA: tokens e custo estimado por dia e por comentário publicado.

## Modelo de dados (rascunho)

- `fishing_sources`: tipo (`perfil` | `hashtag`), valor, ativo, última coleta, contadores.
- `fishing_posts`: fonte, `media_id` (único por workspace), URL, autor, legenda, mídia, métricas, data do post,
  nota, motivo, resumo, status, `aberto_em`, `publicado_em`, usuário, texto publicado, opção escolhida, editado.
- `fishing_drafts`: post, tipo, texto, gerado_em (para "Gerar outras" sem perder o histórico).
- `fishing_settings`: perfil da marca, exemplos, palavras proibidas, nota de corte, limites, janela.
- `contacts.source = 'pesca'` e referência ao `fishing_post` de origem quando houver.

## Fases

1. **MVP com a conexão atual:** link colado → rascunho → fila → confirmação → métricas de operação.
   Valida o valor dos comentários sem depender de App Review.
2. **Menções** com resposta pelo Antares (já suportado pelo Instagram Login; falta assinar o campo `mentions`).
3. **Migração para Unified Login:** ler o guia de migração, testar Business Discovery (quais campos da mídia
   vêm) e Hashtag Search com conta de teste em Standard Access.
4. **Coleta automática:** perfis-alvo e hashtags, triagem e cotas. Para clientes externos, depende de
   Advanced Access, verificação da empresa e aprovação do *Instagram Public Content Access*.
5. **Atribuição** e tela de Resultados completa.

## Riscos e pendências

- App Review do *Instagram Public Content Access* pode demorar ou ser negado; as fases 1 e 2 continuam úteis sem ele.
- A migração para Unified Login mexe na conexão que já atende a Caixa de entrada e as automações; precisa de
  plano próprio para não interromper DMs e comentários.
- A documentação da Meta se contradiz sobre `recent_media`/`top_media` no Unified Login; confirmar em teste.
- Publicar o mesmo tom em volume ainda pode parecer spam aos olhos das pessoas, mesmo feito à mão: os limites e
  a checagem de similaridade existem para isso.
- Fase 1 usa OpenRouter com chave da plataforma no servidor e modelos configuráveis. Repasse de custo não implementado.
- Atribuição de resultado é estimativa; não vender como número exato.
