# Como funciona

Fases sequenciais que se comunicam por tabelas SQLite em `data/vagalume.db`. Cada fase tem uma função `run()`, lê a tabela da anterior e grava a sua. Toda a parametrização fica em `config.py`.

| Fase | Módulo | O que faz | Grava |
|---|---|---|---|
| 1 | `sanity_check` | Redescobre variáveis conhecidas e confere o período medido | (nada; aborta se falhar) |
| 2 | `selecionar_alvos` | Escolhe estrelas de um setor TESS por brilho e baixa contaminação | `alvos` |
| 3 | `baixar_curvas` | Baixa as curvas de luz QLP/TESS-SPOC do MAST, com cache | `curvas` |
| 4 | `detectar_sinal` | Busca periodicidade com Lomb-Scargle e BLS | `sinais` |
| 5 | `cruzar_conhecidos` | Cruza com VSX, ATLAS, TESS-EBs, outros catálogos de variáveis do TESS (inclusive Wang+2025, do China-VO), Gaia DR2/DR3, ZTF, ASAS-SN, TOI e SIMBAD | `sinais_fase5` |
| 6 | `checar_contaminacao` | Descarta sinais que podem vir de estrela vizinha | `candidatos` |
| 7 | `triagem` | Gera uma figura por candidata: curva, curva dobrada em P e 2P, periodograma, campo TESS e mapa do sinal por pixel | `candidatos_fase7` |
| revisão | `app/revisao.py` + `app/paginas/` | App local (Streamlit) para olhar cada candidata e marcar confirmar, dúvida ou descartar | `revisao_humana` |
| 8 | `ficha_vsx` | Para as confirmadas, monta a ficha do VSX: fonte Gaia DR3, V estimada, período medido com todos os setores do TESS (com o erro e um alerta quando os setores não concordam), tipo sugerido, época do mínimo em BJD, amplitude e curva em fase, e refaz a busca no VizieR inteiro (com o VizieR de Estrasburgo fora, só numa lista de 25 catálogos de variáveis num espelho) | `data/vsx/` |

O envio ao VSX é manual (não há API): veja o [passo a passo](comecar.md#passo-a-passo). Tipo e período da ficha são sugestões; confira na curva em fase.
