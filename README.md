# Cartomanic BR

Construtor interativo de mapas classificados do Brasil, até o nível de
município. Você desenha um esquema de categorias (uma legenda), clica nos
municípios pra classificá-los, e o mapa é sempre re-renderizado a partir da
geometria oficial (IBGE, via `geobr`) + dessa classificação — nunca existe
uma "imagem do mapa" salva em lugar nenhum.

Sucessor direto do projeto legado `pybrmania`, reconstruído do zero com uma
separação clara entre dado geográfico (`data/`), regra de negócio
(`engine/`) e interface (`gui/`).

## Instalação (usuário final)

Baixe o instalador mais recente na [página de
Releases](https://github.com/emanuelbarroso/cartomanicbr/releases) --
`CartomanicBR-Setup-<versão>.exe`. Instala por usuário (sem pedir
permissão de administrador), em português brasileiro. Ver
`packaging/README.md` pra detalhes de como esse instalador é gerado.

## Como rodar (desenvolvimento)

```bash
cd cartomanic
source .venv/Scripts/activate   # Windows/Git Bash
python -m cartomanic
```

No PowerShell, sem ativar a venv:

```powershell
.\.venv\Scripts\python.exe -m cartomanic
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
    ibge_source.py      # API de agregados do IBGE -> população e área oficial
  engine/
    snapshot_store.py   # armazenamento com retenção (máx. 5 versões por dataset)
    project.py          # Project: só metadados + tabelas DuckDB, nunca geometria
    classification_io.py# export/import JSON de esquema+classificação
    statistics.py       # contas das Estatísticas gerais (pandas puro, sem GUI)
  gui/
    main_window.py      # janela principal, menus, toolbar, orquestração
    map_canvas.py        # desenho (Tkinter Canvas), zero estado próprio de geometria
    map_tree.py           # árvore de navegação (Brasil > estados incluídos no projeto)
    _insets.py             # detecção automática de ilhas distantes (Fernando de Noronha etc.)
    _projection.py          # bounds/fit/transform de coordenada, compartilhado
    statistics_dialog.py   # janela de Estatísticas gerais (só exibe; contas no engine)
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
  baixado (município via `geobr`, população/área via IBGE, ou uma
  classificação via CSV) — mesmo mecanismo, `append` ou `replace`, nunca
  mistura os dois.
- **API de agregados do IBGE** (`servicodados.ibge.gov.br`), não a SIDRA
  direto — são as mesmas tabelas, mas a SIDRA fica atrás de um desafio
  anti-robô que bloqueia cliente HTTP comum.
- **Estatísticas: contas no `engine/`, janela só exibe** — a mesma
  separação do resto do projeto, e é o que deixa as contas testáveis sem
  abrir nenhuma janela.

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
- Data > Obtain from Internet (com buffer de até 5 snapshots, escolha de
  substituir ou adicionar) e Obtain from CSV (mesmo mecanismo, fonte
  local). Fontes de internet disponíveis:
  - **Municípios** — geometria via `geobr`.
  - **População e área (Censo 2022)** — IBGE, tabela 4714: população
    residente e área territorial *oficial* (km²) de cada município.
  - **População estimada (IBGE)** — tabela 6579: todos os anos publicados
    depois do Censo (hoje 2024–2026).
- Uma cópia de cada um desses datasets vem empacotada no repositório
  (`data/geo_cache/`), então tudo funciona sem internet.
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
  `starts_with` e destaque) e aplicar tudo de uma vez. Checkbox "Ocultar
  municípios já classificados em outra categoria" tira da lista da
  esquerda quem já está em outra categoria (salva ou só pendente), pra
  não puxar por engano; o título da lista mostra quantos foram ocultados.
- Modos de visualização pra esquema hierárquico: Tudo / `=` Exato / `≥`
  Hierarquia (cada modo é uma query DuckDB diferente sobre a mesma tabela).
- Export/Import JSON do esquema + classificação, com validação completa
  (todo erro é acumulado e mostrado de uma vez, nunca aplica parcial).

**Estatísticas gerais** (Data > Estatísticas gerais..., ou botão de
gráfico na barra)
- Janela não-modal com abas **Brasil / Regiões / Estados**: por categoria,
  quantidade de municípios, área oficial (km²) e população, cada uma com
  seu %, mais em quantas UFs a categoria aparece (Brasil e Regiões).
- Linhas: uma por categoria (com a cor), "Sem classificação" e "Total";
  os % são sempre relativos ao Total do grupo e somam 100%.
- População selecionável: Censo 2022 ou qualquer ano de estimativa
  disponível.
- Checkbox "Só estados incluídos no projeto" restringe tudo aos estados
  da árvore.
- Esquema hierárquico segue o modo do mapa: `=` mostra só a categoria
  escolhida, `≥` cada categoria daquela pra cima + um Subtotal; o que o
  modo deixa de fora vai pra "Outras categorias".
- Atualiza sozinha (com debounce) a cada clique, Adição em Série, troca de
  esquema/modo/estados ou projeto — diferente do Preview, nunca fica
  desatualizada.
- Município mais novo que a geometria (ex.: 5101837, que aparece nas
  estimativas a partir de 2025) entra só com a população nos totais de
  estado/região/Brasil, com uma nota no rodapé.

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
- Suite de testes automatizados (44 testes) cobre `engine/`, a leitura
  das respostas da API do IBGE (sem rede) e smoke tests de GUI da Adição
  em Série e das Estatísticas gerais (esses abrem janelas Tk de verdade e
  são pulados onde não há Tk). O resto de `gui/` — canvas, editor de
  esquema, Preview etc. — continua validado só manualmente.
- A soma das áreas oficiais dos municípios dá ~13 mil km² a menos que a
  área do Brasil (provavelmente as lagoas que o IBGE contabiliza à parte);
  os % de área nas Estatísticas usam a soma dos municípios como base.
- Instalador Windows sem ícone customizado e sem assinatura de código --
  o SmartScreen do Windows avisa "editor desconhecido" na primeira
  execução. Ver `packaging/README.md`.

## Sugestões pra próximos passos

1. Estender os testes de `gui/` pros diálogos que ainda não têm (canvas,
   editor de esquema, Preview), no mesmo molde de
   `tests/test_statistics_dialog.py`.
2. Migração leve pra projetos antigos: se `included_states` estiver vazia
   mas existir classificação, inferir os estados a partir dela.
3. Exportar o Preview como imagem/PDF de verdade (hoje é só visualização
   em tela).
4. Lista de "projetos recentes" no menu File.
5. Decidir o que fazer com categorias órfãs ao trocar discreto ↔
   hierárquico (perguntar antes, ou limpar automaticamente).
6. Ícone customizado + assinatura de código pro instalador (ver
   `packaging/README.md`).
7. Exportar as tabelas das Estatísticas gerais pra CSV.

## Licença

MIT -- ver [`LICENSE`](LICENSE).
