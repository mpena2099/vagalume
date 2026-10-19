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
streamlit run app/revisao.py       # revisão visual das candidatas da Fase 7
```

`lightkurve` emite um `UserWarning` sobre `oktopus` ao importar. É inofensivo; use `-W ignore` para silenciar.

**Fase 1 (`sanity_check`) é o teste de aceite.** Redescobre WASP-18 b, a binária eclipsante TIC 142979644 e a binária de contato TIC 121213501, e compara o período medido com a referência (tolerância 0,1%, aceitando harmônicos 0,5x e 2x). Se falhar, `sys.exit(1)`. Use-a para validar que o MAST está respondendo.

## Arquitetura

Fases sequenciais que se comunicam por tabelas SQLite em `data/vagalume.db`, cada uma com `run()` que lê a tabela anterior e grava a sua com `to_sql(..., if_exists="replace")`. Estado atual: as 7 fases existem, mais o app de revisão. Plano das fases em `especificacao.md` seção 3:

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
- `src/cruzar_conhecidos.py` `classificar(matches, periodo_d)`: lógica pura (testável offline). `run()` faz, por estrela com sinal, uma consulta VizieR com todos os catálogos de `CATALOGOS_VIZIER` e `CATALOGOS_GAIA`, uma ao SIMBAD (só `otype` em `SIMBAD_VARIAVEIS`) e cruza com o CSV de TOIs do ExoFOP (cache em `data/toi.csv`). Distância calculada das coordenadas do catálogo, não do `_r` do VizieR. Gaia DR3 só marca `gaia_candidata`, não muda `status`. Grava `sinais_fase5`. No setor 55: 22 novas, 12 conhecidas, 6 conhecidas vizinhas de 40.

- `src/checar_contaminacao.py` `amp_necessaria`, `veredito`: lógica pura. `run()` lê `sinais_fase5` com `status = 'novo'` e, por sinal: (1) vizinhas variáveis até `RAIO_VIZINHA_VARIAVEL_ARCSEC` (120") pelo mesmo `_consultar_vizier` da Fase 5; período compatível descarta (`vizinha_variavel`); (2) fontes Gaia DR3 até 42" com ΔG < 4 e a amplitude intrínseca que precisariam ter; abaixo de `BLEND_AMP_MAX` marca `suspeito_blend`; (3) mede o mesmo método em até 2 outros setores do mesmo produto do alvo (`autor` lido de `alvos`; os setores mais próximos do original); nenhum compatível descarta (`nao_persiste`). Grava `candidatos` com `veredito` e `autor`. Variáveis conhecidas a 50" a 90" com o mesmo período são a principal causa de descarte no setor 55 (pixel do TESS = 21").
- `src/triagem.py`: um sinal por estrela candidata (`escolher_sinal`: maior amplitude/ruído entre os de veredito `candidato`; `sinais_todos` lista também os `nao_persiste`, como contexto). Lê a curva com o `autor` do alvo. Figura 2x3 em `data/triagem/<tic>.png`. O mapa por pixel vem de um recorte TESScut 11x11, com cada pixel destendenciado por polinômio por órbita. LS usa `amplitude_dobrada` (pico a pico em bins de fase); BLS usa `profundidade_eclipse` (fora menos dentro do eclipse), porque com poucos eclipses a mediana por bin apaga o sinal. `deslocamento_px` = distância do pixel de maior sinal ao alvo. `tipo_provavel` e `nota_llm` ficam vazios (LLM não implementada).
- `app/revisao.py` + `app/dados.py`: mesmo padrão do Rastro. `dados.py` não importa Streamlit e é testado offline. Decisões em `revisao_humana` (chave `tic`), fora do `to_sql replace`. Ao testar com `streamlit.testing.v1.AppTest`, não clicar nos botões de decisão: eles gravam no banco real.

O `lk.search_lightcurve` devolve resultado vazio, sem exceção, quando a rede cai. Por isso a Fase 6 exige que a busca contenha o próprio setor original.

Na Fase 4, LS roda sobre `lc.flatten()` com janela de 4 d (`LS_FLATTEN_D`): sem ela o pico cai nas tendências lentas do `sap_flux` (~14 d) e o FAP fica ~0 em toda estrela. BLS usa janela de 1,5 d e recebe `dy` = ruído ponto a ponto; sem `dy` o `astropy` assume erro 1 e o SNR sai ~0,02. A Fase 1 usa LS sem flatten e BLS sem `dy` (só o argmax importa lá).

## Convenções

Código, prints e nomes de tabela/coluna em português. Comentários curtos e raros. Mantenha os prints de progresso. `data/` fica fora do git; `docs/img/` é versionado (figuras do README).
