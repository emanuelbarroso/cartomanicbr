# Cartomanic BR

Construtor interativo de mapas classificados do Brasil, até o nível de
município. Você desenha um esquema de categorias (uma legenda), clica nos
municípios pra classificá-los, e o mapa é sempre re-renderizado a partir da
geometria oficial (IBGE, via `geobr`) + dessa classificação — nunca existe
uma "imagem do mapa" salva em lugar nenhum.

Sucessor direto do projeto legado `pybrmania`, reconstruído do zero com uma
separação clara entre dado geográfico (`data/`), regra de negócio
(`engine/`) e interface (`gui/`).

## Como rodar

```bash
cd cartomanic
source .venv/Scripts/activate   # Windows/Git Bash
python -m cartomanic
```

Rodar os testes:

```bash
python -m pytest tests/ -q
```

## Arquitetura

```
src/cartomanic/
  data/
    geo_source.py       # geobr -> SnapshotStore -> GeoDataFrame pra desenhar
  engine/
    snapshot_store.py   # armazenamento com retenção (máx. 5 versões por dataset)
    project.py          # Project: só metadados + tabelas DuckDB, nunca geometria
    classification_io.py# export/import JSON de esquema+classificação
  gui/
    main_window.py      # janela principal, menus, toolbar, orquestração
    map_canvas.py        # desenho (Tkinter Canvas), zero estado próprio de geometria
    map_tree.py           # árvore de navegação (Brasil > estados incluídos no projeto)
    _insets.py             # detecção automática de ilhas distantes (Fernando de Noronha etc.)
    _projection.py          # bounds/fit/transform de coordenada, compartilhado
    scheme_editor_dialog.py, gradient_dialog.py, bulk_tier_dialog.py,
    obtain_data_dialog.py, preview_dialog.py, state_picker_dialog.py, ...
```

**Regra de ouro que se manteve o projeto inteiro**: `Project` nunca guarda
geometria. Um projeto é só metadados + tabelas pequenas (esquema de
categorias, classificação por município, quais estados foram incluídos). O
mapa é sempre reconstruído combinando isso com a geometria vetorial
empacotada no repositório.

## Decisões de arquitetura

- **Pandas**, não Polars, pras tabelas de classificação — `geopandas` já
  força pandas na árvore de dependências, e a escala (milhares de
  municípios, não milhões) nunca justificaria a troca.
- **DuckDB** como formato de arquivo de projeto (`.cmbr`) — um banco
  embarcado real, com SQL de verdade, em vez de CSV/pickle.
- **GeoParquet**, não GeoJSON, pra geometria — mais compacto (~3,6x menor
  que o GeoJSON do legado) e carregado via `geopandas` (resolveu de
  brinde um bug do parser manual do legado, que descartava anéis internos).
- **Snapshots com retenção (máx. 5)** como padrão único pra qualquer dado
  baixado (município via `geobr`, ou uma classificação via CSV) — mesmo
  mecanismo, `append` ou `replace`, nunca mistura os dois.

## Funcionalidades implementadas

**Projeto**
- Novo/Abrir/Salvar/Salvar Como/Fechar, com detecção de alterações não
  salvas.
- Nome raiz da árvore editável (duplo-clique no cabeçalho) — reflete o que
  o projeto está classificando.
- Um projeto novo começa **sem nenhum estado**; "Adicionar Estado..." (um
  de cada vez) e "Adicionar Tudo" (com confirmação) povoam a árvore.
  "Remover Estado.../Remover Tudo" fazem o inverso — só tiram da árvore,
  **não apagam classificação** (readicionar o estado traz tudo de volta).

**Dado geográfico**
- Data > Obtain from Internet (município via `geobr`, com buffer de até 5
  snapshots, escolha de substituir ou adicionar) e Obtain from CSV (mesmo
  mecanismo, fonte local).
- Ilhas distantes (Fernando de Noronha/PE, Trindade e Martim Vaz/ES — essa
  é só *parte* do polígono de Vitória) são detectadas automaticamente
  (dissolve de geometria + teste de distância real, não uma lista de nomes
  hardcoded) e desenhadas num quadro à parte, ampliadas, em vez de esticar
  o mapa principal.

**Classificação**
- Esquema **discreto** ou **hierárquico** (editor com adicionar/remover/
  reordenar/cor, "Adicionar Várias" em lote com nomes genéricos `Cxx`).
- Gerador de gradiente de cor (2 cores + 4 receitas: RGB linear, RGB
  suavizado, HSV caminho curto/longo) pra colorir um esquema hierárquico
  inteiro de uma vez — preview com um bloco por categoria real, não uma
  rampa abstrata.
- Clique esquerdo no mapa cicla pelas categorias; clique direito apaga a
  classificação do município direto.
- Adição em Série: mover municípios entre duas listas (com busca
  `starts_with` e destaque) e aplicar tudo de uma vez.
- Modos de visualização pra esquema hierárquico: Tudo / `=` Exato / `≥`
  Hierarquia (cada modo é uma query DuckDB diferente sobre a mesma tabela).
- Export/Import JSON do esquema + classificação, com validação completa
  (todo erro é acumulado e mostrado de uma vez, nunca aplica parcial).

**Mapa**
- Hover mostra nome do município + UF (ou nome do estado, na visão Brasil).
- Preview de impressão: papel A0–A5, retrato/paisagem, legenda opcional.
- Redesenha sozinho ao redimensionar a janela (com debounce).

## Performance

- Split ilha/continente é cacheado por estado — o cálculo (dissolve de
  geometria) é caro (~2s num estado com 850+ municípios) e não muda entre
  redesenhos do mesmo estado.
- Classificar um único município (ou aplicar um lote) recolore só os
  polígonos afetados via tag do Tkinter Canvas, em vez de redesenhar o
  estado inteiro do zero.
- Nenhuma rolagem de mouse desnecessária: o Canvas sempre se ajusta ao
  tamanho disponível, então rolar não tinha função — e causava
  dessincronia de clique quando existia.

## Limitações conhecidas / pendências

- **Ainda não é um repositório git.** Muito trabalho em disco, zero
  histórico de commit.
- Preview de impressão é uma **foto do momento em que abre** — não
  atualiza sozinho se você trocar de estado ou reclassificar com ele
  aberto.
- Abrir um projeto salvo **antes** da funcionalidade de "estados
  incluídos" existir vai mostrar a árvore vazia (a tabela nova começa
  zerada) mesmo que o projeto já tenha municípios classificados — não
  fizemos nenhuma migração automática. Contorno: "Adicionar Tudo" uma vez.
- Trocar o esquema de Hierárquico pra Discreto (ou vice-versa) num projeto
  que já tem município classificado não avisa nem limpa nada — pode deixar
  categoria "órfã" sem aparecer em nenhum modo de visualização.
- Cache do `GeoDataFrame` carregado (item "3" da discussão de performance)
  não foi implementado — cada troca de estado ainda relê o parquet do
  Brasil inteiro (~0,1s, hoje irrelevante perto do resto).
- Suite de testes automatizados cobre só `engine/` (24 testes). Toda a
  validação de `gui/` feita ao longo do projeto foi manual, sessão a
  sessão — não existe teste de regressão pra diálogo/canvas.
- Sem empacotamento pra distribuição (instalador, `.exe`) — hoje só roda
  via `python -m cartomanic` dentro da `.venv` de desenvolvimento.

## Sugestões pra próximos passos

1. **`git init` + primeiro commit** — prioridade alta, é risco real de
   perda de trabalho.
2. Testes automatizados de `gui/` (mesmo que só os smoke tests que fizemos
   manualmente, formalizados em `tests/`).
3. Migração leve pra projetos antigos: se `included_states` estiver vazia
   mas existir classificação, inferir os estados a partir dela.
4. Exportar o Preview como imagem/PDF de verdade (hoje é só visualização
   em tela).
5. Lista de "projetos recentes" no menu File.
6. Decidir o que fazer com categorias órfãs ao trocar discreto ↔
   hierárquico (perguntar antes, ou limpar automaticamente).
