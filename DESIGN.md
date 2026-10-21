# Antares CRM — sistema visual

Identidade: ícone de órbita em vermelho `#e60000`.

A interface tem uma base única e contínua: sidebar tinta (`#25282b`) e área de trabalho
neutra, sem topbar nem uma moldura externa envolvendo toda a página.
A navegação permanece em lista única, sem agrupamentos e sem bloco de espaço de
trabalho. Recolher/expandir mantém animação e preferência salva.

## Tokens e componentes

`frontend/src/app/globals.css` define os tokens, a estrutura e os componentes
compartilhados. `frontend/src/app/modules.css` contém os layouts específicos de
funil, tabelas com paginação, agenda, diálogos e conversas. Não adicionar uma
camada de tema para sobrescrever o sistema: alterar o componente na sua origem.

Referência: `vodafone-DESIGN.md` (vermelho de marca, tinta e escala de cinzas), adaptada
a uma ferramenta densa de trabalho. Os tamanhos de fonte do app não mudam.

| Uso | Valor |
|---|---|
| Ação principal / marca | `#e60000` (hover `#b80000`) |
| Tinta: sidebar, bordas de campos, botões secundários | `#25282b` |
| Área de trabalho | `#f2f2f2` |
| Superfícies | `#ffffff` |
| Texto secundário | `#6b6e71` |
| Divisórias | `#e1e1e1` |
| Seleção discreta | `#fdecec` |

Sem segunda cor de destaque. Inter (substituta da Vodafone), títulos em caixa alta peso 800.
Botões em pílula (60px): primário vermelho, secundário contorno tinta. Abas e selos em pílula.
Cartões planos, raio de 6px, sem sombras; profundidade vem do contraste entre a sidebar
tinta e a área clara. Campos com borda tinta de 1px, raio 6px e foco vermelho.
A cor das etapas do funil é dado do usuário e não faz parte do tema.

Login apenas com formulário e cadastro público desativado. Em telas pequenas,
menu em gaveta e formulários adaptáveis. Respeitar preferência por movimento
reduzido e preservar nomes acessíveis nos ícones da sidebar recolhida.

Prévia visual usa fixtures somente em proxy localhost, sem gravar dados de
exemplo no banco. Nunca exibir números ou conexões fictícias na aplicação real.

## Espaçamento

Escala de 4px, definida em `:root` de `globals.css`. Todo `padding`, `margin` e `gap`
usa um destes degraus; valores fora da escala (3, 5, 6, 10, 14, 18, 20px…) não são usados.

| Token | Valor | Uso |
|---|---|---|
| `--space-1` | 4px | ajustes mínimos, entre ícone e texto colado |
| `--space-2` | 8px | `--gap-inline`: ícone + rótulo, botões em linha, chips |
| `--space-3` | 12px | `--gap-group`: barras de ferramentas, itens de lista |
| `--space-4` | 16px | `--gap-section` e `--pad-card`: entre cartões; interior de cartões |
| `--space-5` | 24px | margem lateral da página; respiro de blocos grandes |
| `--space-6` | 32px | raro: estados vazios e áreas de destaque |

Papéis: página `16px` vertical e `24px` lateral (`--page-pad-y/x`); cartão `16px`;
cabeçalho de cartão `12px 16px` com mínimo de 48px; célula de tabela `12px 16px`;
campo de formulário com `8px` entre rótulo e controle. No celular, página com `16px`
e cartões com `12px` laterais. Exceções legítimas: compensações de ícone dentro de
campos (ex.: `padding-right` para o botão de senha) e alturas fixas de linhas
calculadas em `fit.tsx`.

## Área de trabalho

Cabeçalhos internos exibem título e ações, sem slogans ou descrições introdutórias.
Margens e distâncias seguem a seção Espaçamento.
Conteúdo usa a largura disponível. Manter fonte das tabelas e alvos dos botões.
Textos de confirmação, consentimento, erros, unidades, datas e dados cadastrados
não devem ser removidos por critérios de densidade. Instruções de formulários
permanecem quando evitam erros ou explicam consequências.
