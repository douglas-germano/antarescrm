# Grafo de impacto do Antares

Antes de alterar código, consulte o mapa local quando o Neo4j estiver disponível:

```bash
python3 scripts/code-graph.py status
# Se fresh=false ou ainda não houver snapshot:
python3 scripts/code-graph.py sync
python3 scripts/code-graph.py impact backend/app/services/history.py
python3 scripts/code-graph.py search ingest
```

Use o caminho relevante à tarefa. `impact --changed` consulta as alterações do Git.
As consultas de impacto e busca recusam snapshots desatualizados. Depois das alterações,
sincronize novamente antes de consultar o impacto final.

Use as referências de arquivo/linha para ler o código e selecionar os testes. Dependências
estáticas são candidatas a impacto; `origin=inferred` exige revisão. Relações `VERIFIED_BY`
indicam testes associados por curadoria, não testes executados ou cobertura comprovada.
Confira `truncated` e `unindexed`: resultados limitados e arquivos fora do índice exigem
investigação adicional. O grafo não substitui `scripts/check.sh` nem validação funcional.

Se o banco estiver indisponível, prossiga com busca e leitura do código e informe essa
limitação. Para iniciar o serviço local autorizado, use `python3 scripts/code-graph.py init`.
Não leia nem imprima o arquivo de credenciais para diagnosticar erros.

Operação, modelo e limites: [docs/GRAFO-DE-CODIGO.md](docs/GRAFO-DE-CODIGO.md).
