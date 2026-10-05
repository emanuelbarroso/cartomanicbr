# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento: [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Unreleased]

## [1.0.0] - 2026-10-05

Primeira versão pública. Reconstrução completa do legado `pybrmania`.

### Adicionado

**Projeto**
- Novo/Abrir/Salvar/Salvar Como/Fechar, com detecção de alterações não
  salvas e confirmação antes de descartar.
- Arquivo de projeto `.cmbr` (DuckDB) -- só metadados e tabelas pequenas,
  nunca geometria.
- Nome raiz da árvore editável, refletindo o que o projeto classifica.
- Um projeto novo começa sem nenhum estado; "Adicionar Estado"/"Adicionar
  Tudo" (com confirmação) povoam a árvore; "Remover Estado"/"Remover Tudo"
  fazem o inverso sem apagar classificação já feita.

**Dado geográfico**
- Data > Obtain from Internet (município via `geobr`/IBGE) e Obtain from
  CSV, com buffer de retenção de até 5 snapshots por dataset (substituir
  ou adicionar).
- Geometria de estados/municípios empacotada como GeoParquet.
- Detecção automática de ilhas geograficamente distantes (Fernando de
  Noronha/PE, Trindade e Martim Vaz/ES) via dissolve de geometria + teste
  de distância real -- desenhadas num quadro ampliado à parte, sem
  distorcer a escala do mapa principal.

**Classificação**
- Esquemas de legenda discretos ou hierárquicos, com editor completo
  (adicionar, adicionar várias em lote, remover, reordenar, cor).
- Gerador de gradiente de cor (2 cores + 4 receitas de interpolação) pra
  colorir um esquema hierárquico inteiro de uma vez.
- Clique esquerdo no mapa cicla categorias; clique direito limpa a
  classificação do município.
- "Adição em Série": mover municípios entre duas listas (com busca e
  destaque) e aplicar tudo de uma vez.
- Modos de visualização hierárquica: Tudo / `=` Exato / `≥` Hierarquia.
- Export/Import JSON do esquema + classificação, com validação completa
  antes de aplicar qualquer coisa (todo erro é acumulado e mostrado de
  uma vez).

**Mapa**
- Canvas interativo com hover (nome de município/UF ou estado),
  zoom, e redesenho automático (com debounce) ao redimensionar a janela.
- Preview de impressão: papéis A0-A5, retrato/paisagem, legenda opcional.

**Performance**
- Cache por estado do split ilha/continente (o cálculo geométrico mais
  caro do projeto).
- Recolorir incremental (por tag do Canvas) em vez de redesenhar o mapa
  inteiro a cada classificação.

**Distribuição**
- Empacotamento Windows via PyInstaller (`--onedir`) + instalador Inno
  Setup (LZMA2/ultra64, ~75% de compressão sobre a pasta instalada,
  instalação por usuário sem UAC, português brasileiro).

### Testes

- 24 testes automatizados cobrindo `engine/` (snapshot store, projeto,
  import/export de classificação). Camada `gui/` validada manualmente ao
  longo de todo o desenvolvimento.

[Unreleased]: https://github.com/emanuelbarroso/cartomanicbr/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/emanuelbarroso/cartomanicbr/releases/tag/v1.0.0
