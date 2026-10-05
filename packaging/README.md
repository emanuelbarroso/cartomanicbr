# Empacotando Cartomanic BR em `.exe` (Windows)

## Build

```bash
cd cartomanic
.venv/Scripts/pyinstaller packaging/cartomanic.spec --clean --noconfirm
```

Saída em `dist/CartomanicBR/` (modo `--onedir`, não `--onefile` -- ver
"Por que onedir" abaixo). Pra testar sem afetar uma cópia já em uso, use
`--distpath`/`--workpath` apontando pra outro diretório.

## Por que onedir, não onefile

`--onefile` empacota tudo num `.exe` só, mas **descompacta pra uma pasta
temp toda vez que o programa abre**. Com essa pilha de dependência (300MB+),
isso significa alguns segundos de espera a cada abertura, só pra
descompactar algo que não mudou desde a última vez. `--onedir` paga esse
custo uma vez (na instalação), não a cada clique duplo.

## Por que nada de UPX

UPX comprime o `.exe`/DLLs individualmente. Testamos a ideia geral e
descartamos por três motivos, nenhum deles específico de implementação:
1. Os maiores itens (`pyarrow`, GDAL via `pyogrio`, `duckdb`) já são
   binários nativos otimizados -- UPX ganha pouco ou nada neles.
2. Single-file comprimido com UPX é um padrão clássico de falso-positivo
   de antivírus.
3. Compressão de verdade pra distribuição deve ficar pro instalador
   (Inno Setup, LZMA2), que comprime o pacote inteiro de uma vez sem
   tocar nos binários -- mais seguro e geralmente comprime melhor.

## Poda de tamanho (validada)

`packaging/cartomanic.spec` remove, de `pyarrow` e `pyogrio`, componentes
confirmados como não usados por este app. **Nada foi cortado por suposição**
-- cada item da lista `_UNUSED_SUBSTRINGS` no `.spec` foi validado assim:

1. Os arquivos suspeitos foram **movidos** (não apagados) pra fora da
   `.venv` de desenvolvimento.
2. Rodamos a suite de testes inteira (`pytest tests/ -q`) + um round-trip
   manual de `GeoDataFrame` real via `SnapshotStore` (exatamente o caminho
   que usa `pyarrow` em produção: `to_parquet`/`read_parquet`).
3. Com tudo passando, os arquivos foram restaurados na `.venv` (nunca
   deixamos a `.venv` de desenvolvimento mutada).
4. O mesmo corte foi **revalidado dentro do `.exe` congelado**: o
   `packaging/entrypoint.py` tem um modo de autoteste temporário
   (`CARTOMANIC_SMOKE_TEST=<caminho> ./CartomanicBR.exe`) que roda esse
   mesmo round-trip de dentro do executável e escreve PASS/FAIL num
   arquivo (um app `console=False` não tem stdout visível). Isso importa
   porque o jeito que o Windows resolve DLL em um `.exe` congelado não é
   garantidamente idêntico ao `import` normal de um pacote instalado.

Resultado: **319MB → 286MB** (~10%), sem nenhuma funcionalidade afetada.

O que foi cortado e por quê:

| Item | Tamanho | Por quê é seguro remover |
|---|---|---|
| `arrow_flight.dll` + `_flight.*.pyd` | ~15M | Arrow Flight (RPC) -- nunca importado |
| `arrow_dataset.dll` + `_dataset.*.pyd` | ~2M | API de descoberta de dataset -- `geopandas` usa só `pyarrow.parquet`, não isso |
| `arrow_substrait.dll` | 2.7M | Serialização de plano de query Substrait -- não usado |
| `include/`, `src/` (pyarrow) | ~6.5M | Headers C++ e fontes de desenvolvimento -- nunca carregados em runtime, sob nenhuma hipótese |
| `*.lib` (pyarrow) | ~6M | Arquivos de linkagem estática -- só usados compilando contra pyarrow em C++, não em runtime Python |
| `pyarrow/tests/`, `pyogrio/tests/` | ~1M | Suíte de teste das próprias libs -- nunca importada pelo nosso código |

**Se você atualizar `pyarrow` ou `pyogrio` no futuro, revalide essa lista**
-- uma versão nova pode mudar dependência interna entre esses componentes
sem aviso. O processo acima (passos 1-4) é rápido (~5 min) e é a única
forma confiável de confirmar, não tem atalho seguro.

## Avisos do build (conhecidos, inofensivos)

- `WARNING: Datas for pyproj not found at: .venv\Library\share\proj` --
  esse caminho é de instalação via conda; nós instalamos via pip, e os
  dados do PROJ vêm empacotados dentro do próprio pacote `pyproj`
  (`pyproj/proj_dir/`), que é coletado normalmente. Aviso cosmético do
  hook, não indica dado faltando.
- `WARNING: Failed to collect submodules for 'duckdb.experimental'` --
  módulo opcional do `duckdb` que não usamos (precisa de
  `typing_extensions`, que não é dependência nossa).
- `WARNING: Hidden import "jinja2" not found!` -- dependência opcional do
  `pandas.DataFrame.style`, não usamos.

## Oportunidades de poda NÃO aplicadas (precisam de validação própria)

Identificadas mas deliberadamente **não tocadas** nesta rodada -- cada uma
tem risco real de quebrar algo silenciosamente, e exigiria o mesmo processo
de validação de 4 passos acima antes de ir pra produção:

- **Dados de grade do PROJ** (`pyproj/proj_dir/share/proj/*.tif`, grades de
  transformação de datum). Alguns desses arquivos são só pra
  transformações de alta precisão entre sistemas de referência que talvez
  nunca usemos (o projeto trabalha com SIRGAS2000/EPSG:4674, dado do
  IBGE). Risco: cortar a grade errada produz coordenada levemente errada
  silenciosamente, sem crash -- o pior tipo de bug pra um app de mapa.
- **Drivers do GDAL dentro de `pyogrio.libs`** -- hoje é uma DLL
  monolítica com todo o GDAL; não dá pra podar por formato sem recompilar
  o GDAL com menos drivers habilitados. Trabalho de build bem maior, fora
  de escopo de uma poda de spec file.
- **Trocar `pyarrow`/Parquet por outra coisa** (ex: `fastparquet`) --
  eliminaria ~45MB restantes de `pyarrow` de vez, mas é mudança de
  arquitetura (trocar a lib de serialização do `SnapshotStore`), não poda.

## Instalador (Inno Setup)

`packaging/cartomanic.iss` compila `dist/CartomanicBR/` (já podada, ver
acima) num instalador único com compressão LZMA2/ultra64 + solid
compression -- esse é o lugar certo pra "melhor compressão", não UPX nos
binários (ver "Por que nada de UPX" acima).

### Instalar o compilador (uma vez só)

```powershell
winget install --id JRSoftware.InnoSetup -e
```

Instala em `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` (per-user, sem
precisar de admin).

### Compilar

```bash
cd cartomanic
"/c/Users/<você>/AppData/Local/Programs/Inno Setup 6/ISCC.exe" packaging/cartomanic.iss
```

Requer que `dist/CartomanicBR/` já exista (rode o PyInstaller primeiro).
Saída em `installer_output/CartomanicBR-Setup-<versão>.exe`.

### Resultado medido

| | Tamanho |
|---|---|
| `dist/CartomanicBR/` (pasta instalada, já podada) | 286MB |
| `CartomanicBR-Setup-0.1.0.exe` (instalador LZMA2) | **70MB** |

~75% de compressão -- confirma na prática que comprimir o pacote de
distribuição inteiro com LZMA2 (Inno) bate muito mais forte que comprimir
binário por binário com UPX nos `.dll`/`.pyd` já otimizados.

### Decisões do `.iss`

- **Instalação por usuário** (`PrivilegesRequired=lowest`, instala em
  `{localappdata}\Programs\CartomanicBR`) -- não pede elevação UAC. Um
  app de hobby pra montar mapa não tem motivo pra exigir admin.
- **Idioma português brasileiro** como padrão (Inno Setup já traz
  `BrazilianPortuguese.isl` pronto), com inglês como alternativa.
- **`AppId` é um GUID fixo**, escrito como literal puro (`{{GUID}`), não
  via `#define` + `{#Nome}` -- misturar o pré-processador do Inno com o
  escape de chave dupla do compilador (`{{`) na mesma linha é uma pegadinha
  clássica: o pré-processador consome uma das chaves de abertura como
  parte do próprio token, deixando o compilador com um `{{` desbalanceado.
  Erro visto durante o desenvolvimento: `A "}" is missing at the end of
  the constant`. Uma linha sem `#` nela nunca passa pelo pré-processador,
  então o literal puro evita o problema de vez. **Nunca mude esse GUID**
  entre versões -- é como o Windows reconhece "é o mesmo app, versão
  diferente" pra upgrade/desinstalação funcionarem direito.

## Próximos passos (fora desta rodada)

- Ícone customizado pro `.exe`/instalador (hoje usa o ícone padrão do
  PyInstaller).
- Assinatura de código (code signing) -- sem isso, o Windows SmartScreen
  vai avisar "editor desconhecido" na primeira execução do instalador.
- Automatizar o build (script único que roda PyInstaller + ISCC em
  sequência, checando pré-requisitos).
