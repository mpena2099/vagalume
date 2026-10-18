# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é

Pipeline pessoal que procura **estrelas variáveis não catalogadas** (binárias eclipsantes, pulsantes, rotacionais) nas curvas de luz públicas do **TESS**, descarta as conhecidas e entrega candidatas para submissão ao **VSX** da AAVSO. Projeto irmão do Rastro (`~/Projetos/Rastro`), com o mesmo contrato de fases.

A especificação completa está em `especificacao.md`: cortes, catálogos de cross-match, riscos, checklist do VSX.

## Comandos

Rodar da raiz do repositório. O venv já existe em `venv/`.

```bash
source venv/bin/activate
export PYTHONUNBUFFERED=1
python pipeline.py                 # fases implementadas, em sequência
python tests/test_units.py         # testes offline (ou: python -m pytest -q tests)
python -c "from src.sanity_check import run; run()"   # uma fase isolada
```

`lightkurve` emite um `UserWarning` sobre `oktopus` ao importar. É inofensivo; use `-W ignore` para silenciar.

**Fase 1 (`sanity_check`) é o teste de aceite.** Redescobre WASP-18 b, a binária eclipsante TIC 142979644 e a binária de contato TIC 121213501, e compara o período medido com a referência (tolerância 0,1%, aceitando harmônicos 0,5x e 2x). Se falhar, `sys.exit(1)`. Use-a para validar que o MAST está respondendo.

## Arquitetura

Fases sequenciais que se comunicam por tabelas SQLite em `data/vagalume.db`, cada uma com `run()` que lê a tabela anterior e grava a sua com `to_sql(..., if_exists="replace")`. Estado atual: Fases 1 a 4 existem. Plano das fases em `especificacao.md` seção 3:

```
Fase 2 selecionar_alvos    → alvos
Fase 3 baixar_curvas       → curvas
Fase 4 detectar_sinal      → sinais
Fase 5 cruzar_conhecidos   → sinais_fase5
Fase 6 checar_contaminacao → candidatos
Fase 7 triagem             → candidatos_fase7
```

**`config.py` é a fonte única de parametrização**: caminhos, `AUTORES_PREFERIDOS`, grade de período, `SANITY_TARGETS`.

Módulos reaproveitáveis pelas próximas fases:
- `src/curvas.py` `baixar_curva(tic, setor=None, autor=None) -> (lc, meta)`: com `setor` e `autor` e cache presente, lê direto sem consultar o MAST; senão busca no MAST, escolhe o primeiro autor de `AUTORES_PREFERIDOS` (`QLP`, `TESS-SPOC`, `SPOC`; strings confirmadas na coluna `author`), cache em `data/curvas/<tic>_s<setor>_<autor>.fits` (só `time, flux, flux_err, cadenceno, quality`; no QLP `flux` é o `sap_flux`), FITS truncado no cache do lightkurve é apagado antes do retry, máscara `quality == 0`, normaliza.
- `src/periodo.py`: lógica pura sobre arrays numpy (testável offline). `medir_periodo_ls` (Lomb-Scargle) e `medir_periodo_bls` (BoxLeastSquares), ambos com uma grade grossa e depois um refinamento em volta do pico; sem o refinamento o erro em 27 dias de dados é ~1%. `comparar_periodo` aceita as razões 1, 0,5 e 2.
- `src/selecionar_alvos.py` `filtrar_alvos(tic, obs, setor)`: lógica pura sobre DataFrames (testável offline). `run()` faz duas consultas ao MAST no mesmo cone (`Catalogs.query_criteria` do TIC com filtro de Tmag/contratio no servidor e `Observations.query_criteria` por `provenance_name` e `sequence_number`), cruza por `target_name` == TIC e sorteia `ALVO_MAX` com semente fixa. Cada consulta leva ~45 s. Campo padrão: setor 55, Cygnus (l=80°, b=0°), raio 1°.
- `src/baixar_curvas.py`: baixa as curvas de `alvos` com `ProcessPoolExecutor` (`CURVAS_WORKERS`). Threads não servem: o lightkurve troca `sys.stdout` global durante o download. Grava `curvas` com `n_pontos`, `duracao_d`, `cadencia_min`, `ruido_ptp` (MAD das diferenças sucessivas, base do corte de amplitude da Fase 4), `desvio`, `status`, `erro`. Setor 55 QLP: 10 min de cadência, ~3700 pontos, ruído mediano ~2,3 ppt. Com cache, a fase roda em segundos.
- `src/util.py` `retry(fn, servico)`: MAST e VizieR são instáveis; toda chamada de rede passa por ele.

- `src/detectar_sinal.py` `avaliar_sinal(...)`: cortes puros (testável offline), devolve o motivo da rejeição ou `None`. `run()` grava em `sinais` uma linha por estrela e método (`ls`, `bls`), com `sinal` e `motivo`; a Fase 5 deve ler só `sinal = 1`. `amplitude` é pico a pico no LS (2x a semi-amplitude) e profundidade no BLS. Também salva `data/figuras/fase4_sinais.png` com os 12 sinais mais fortes. ~30 min para 500 estrelas em 4 processos, quase tudo no BLS.

Na Fase 4, LS roda sobre `lc.flatten()` com janela de 4 d (`LS_FLATTEN_D`): sem ela o pico cai nas tendências lentas do `sap_flux` (~14 d) e o FAP fica ~0 em toda estrela. BLS usa janela de 1,5 d e recebe `dy` = ruído ponto a ponto; sem `dy` o `astropy` assume erro 1 e o SNR sai ~0,02. A Fase 1 usa LS sem flatten e BLS sem `dy` (só o argmax importa lá).

## Convenções

Código, prints e nomes de tabela/coluna em português. Comentários curtos e raros. Mantenha os prints de progresso. `data/` fica fora do git; `docs/img/` é versionado (figuras do README).
