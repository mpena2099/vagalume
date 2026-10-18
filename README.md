# Vagalume

Pipeline pessoal de mineração de dados astronômicos que procura **estrelas variáveis ainda não catalogadas** nas curvas de luz públicas do satélite **TESS** (NASA), descarta as já conhecidas e entrega candidatas prontas para submissão ao **VSX**, o catálogo internacional de estrelas variáveis da AAVSO.

![Ilustração artística de uma binária eclipsante](docs/img/eso1311a.jpg)

*Ilustração artística de uma binária eclipsante: duas estrelas em órbita passam uma na frente da outra, e o brilho somado cai a cada eclipse. Crédito: ESO/L. Calçada, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).*

## Em palavras simples

**A pergunta:** entre milhões de estrelas observadas pelo TESS, quais mudam de brilho e ainda não estão em nenhum catálogo?

**O que se procura:** estrelas que "piscam". Algumas são pares de estrelas que se eclipsam uma à outra (binárias eclipsantes). Outras pulsam, incham e encolhem. Outras giram com manchas na superfície. Em todos os casos o brilho sobe e desce num ritmo regular.

**Como achar:** o TESS mede o brilho de cada estrela a cada poucos minutos, durante semanas. Esse registro se chama *curva de luz*. O software procura nela um padrão que se repete, mede o período, verifica se o objeto já é conhecido e descarta sinais falsos, como a luz de uma estrela vizinha vazando para o mesmo pixel.

![Curva de luz da binária eclipsante TIC 142979644](docs/img/curva_binaria_eclipsante.png)

*Binária eclipsante TIC 142979644, período de 4,179 dias. Em cima, o brilho ao longo de um setor do TESS: as quedas são os eclipses. Embaixo, a mesma curva dobrada no período, com os dois eclipses (primário e secundário) sobrepostos. Gerada pela Fase 1 do pipeline. Dados: NASA/TESS via MAST, produto QLP.*

**A recompensa:** uma variável nova aceita no VSX entra no catálogo com o nome de quem a descobriu.

## Como funciona

Fases sequenciais que se comunicam por tabelas SQLite em `data/vagalume.db`. Cada fase tem uma função `run()`, lê a tabela da anterior e grava a sua. Toda a parametrização fica em `config.py`.

| Fase | Módulo | O que faz | Grava |
|---|---|---|---|
| 1 | `sanity_check` | Redescobre variáveis conhecidas e confere o período medido | (nada; aborta se falhar) |
| 2 | `selecionar_alvos` | Escolhe estrelas de um setor TESS por brilho e baixa contaminação | `alvos` |
| 3 | `baixar_curvas` | Baixa as curvas de luz QLP/TESS-SPOC do MAST, com cache | `curvas` |
| 4 | `detectar_sinal` | Busca periodicidade com Lomb-Scargle e BLS | `sinais` |
| 5 | `cruzar_conhecidos` | Cruza com VSX, TESS-EBs, Gaia DR3, ZTF, ASAS-SN, TOI e SIMBAD | `sinais_fase5` |
| 6 | `checar_contaminacao` | Descarta sinais que podem vir de estrela vizinha | `candidatos` |
| 7 | `triagem` | Gera uma figura por candidata: curva, curva dobrada em P e 2P, periodograma, campo TESS e mapa do sinal por pixel | `candidatos_fase7` |
| revisão | `app/revisao.py` | App local (Streamlit) para olhar cada candidata e marcar confirmar, dúvida ou descartar | `revisao_humana` |

A submissão ao VSX é manual, seguindo o checklist da especificação.

## Estado

As sete fases estão implementadas. A Fase 1 redescobre WASP-18 b, uma binária eclipsante destacada e uma de contato, com o período dentro de 0,1% da referência. A primeira varredura, no setor 55 (Cygnus, plano da Via Láctea), processou 500 estrelas: 40 com sinal periódico, 22 sem variável catalogada a menos de 30" e 15 candidatas depois da checagem de vizinhas e da repetição em outros setores. Elas aguardam a revisão visual. Detalhes técnicos, cortes, catálogos e riscos em [`especificacao.md`](especificacao.md).

## Uso

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export PYTHONUNBUFFERED=1
python pipeline.py              # roda as fases implementadas
python tests/test_units.py      # testes offline (ou pytest)
streamlit run app/revisao.py    # revisão visual das candidatas
```

As decisões da revisão ficam na tabela `revisao_humana`, que o pipeline nunca recria.

As curvas baixadas ficam em cache em `data/curvas/` e as figuras de triagem em `data/triagem/`.

## Dados e créditos

- Curvas de luz: missão TESS (NASA), via [MAST](https://archive.stsci.edu/), produtos [QLP](https://archive.stsci.edu/hlsp/qlp) e [TESS-SPOC](https://archive.stsci.edu/hlsp/tess-spoc).
- Catálogos de variáveis: [VSX/AAVSO](https://vsx.aavso.org), [TESS-EBs](https://archive.stsci.edu/hlsp/tess-ebs), Gaia DR3, ZTF, ASAS-SN, via [VizieR](https://vizier.cds.unistra.fr/).
- Projeto irmão: Rastro, caça a anãs marrons por movimento próprio no CatWISE2020.

## Licença

Código sob a licença [MIT](LICENSE). Imagens de terceiros mantêm a licença indicada na legenda.
