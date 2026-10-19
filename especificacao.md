# Vagalume: especificação técnica

Pipeline pessoal que procura estrelas variáveis ainda não catalogadas (binárias eclipsantes, pulsantes, rotacionais) nas curvas de luz públicas do TESS, descarta o que já é conhecido e entrega candidatos prontos para submissão ao VSX da AAVSO.

O nome vem do inseto que pisca: o projeto procura estrelas que piscam e que ninguém anotou ainda.

## 1. Objetivo e recompensa

Meta principal: o software achar pelo menos uma variável não catalogada e ela ser aceita no VSX (International Variable Star Index, da AAVSO), com o usuário como descobridor.

Marcos, em ordem, cada um já é uma recompensa:

1. **Sanidade:** o pipeline redescobre uma variável conhecida e mede o período certo.
2. **Primeira varredura:** algumas centenas de estrelas processadas, sinais periódicos encontrados, a maioria batendo com catálogos (prova de que a detecção funciona).
3. **Primeiro candidato:** um sinal que sobrevive ao cross-match e à checagem de contaminação.
4. **Submissão aceita no VSX.**

## 2. Por que TESS

- Cobre quase o céu todo em setores de cerca de 27 dias, com cadência de 200 s a 30 min nas imagens de campo inteiro (FFI).
- Existem curvas de luz já prontas, sem processar imagem:
  - **QLP** (Quick-Look Pipeline, MIT): todas as estrelas com magnitude TESS T < 13,5, fluxo bruto e corrigido. Milhões de alvos por ano de missão.
  - **TESS-SPOC** (FFI): até ~160 mil alvos por setor, seleção mais restrita, qualidade alta.
  - **SPOC 2-min**: alvos escolhidos pela missão, mais ruidosos de achar algo novo porque são os mais estudados.
- `lightkurve` baixa tudo isso do MAST em poucas linhas.

Foco nos produtos FFI (QLP e TESS-SPOC): é onde há mais estrelas que ninguém examinou individualmente.

## 3. Arquitetura

Mesmo contrato do Rastro: fases sequenciais, cada uma com `run()`, comunicando por tabelas em `data/vagalume.db` (SQLite, `to_sql(..., if_exists="replace")`). Toda parametrização em `config.py`. Código, prints e nomes de tabela/coluna em português.

```
Fase 1 sanity_check       → (não grava; valida e imprime)
Fase 2 selecionar_alvos   → alvos
Fase 3 baixar_curvas      → curvas          (arquivos em data/curvas/, metadados na tabela)
Fase 4 detectar_sinal     → sinais
Fase 5 cruzar_conhecidos  → sinais_fase5    (adiciona status e match_catalogo)
Fase 6 checar_contaminacao→ candidatos      (só status='novo')
Fase 7 triagem            → candidatos_fase7 (gráficos + nota opcional da LLM)
```

A Fase 8 (`src/ficha_vsx.py`, fora do `pipeline.py`) monta a ficha de cada candidata confirmada; o envio ao VSX é manual, guiado pelo checklist da seção 11.

### Stack

`lightkurve`, `astropy` (`LombScargle`, `BoxLeastSquares`), `astroquery` (MAST, VizieR, Gaia), `pandas`, `numpy`, `matplotlib`, `httpx` (LLM, reaproveitando o módulo do Rastro).

## 4. Fase 1: sanity check

Teste de aceite, como a Fase 1 do Rastro. Se falhar, `sys.exit(1)`.

- Alvo A: uma binária eclipsante do catálogo TESS-EBs (Prša et al. 2022) com período conhecido e T entre 10 e 12.
- Alvo B: um trânsito planetário conhecido e raso, como WASP-18 b (período ~0,94 d), para validar o BLS.
- Critério: período medido dentro de 0,1% do valor de referência (ou de um harmônico 2x/0,5x, registrado como tal).

## 5. Fase 2: selecionar alvos

- Entrada: setor TESS e, opcionalmente, um recorte de céu (RA/Dec + raio) em `config.py`.
- Busca no MAST as curvas QLP/TESS-SPOC disponíveis no setor.
- Cortes iniciais:
  - `ALVO_TMAG_MIN = 9`, `ALVO_TMAG_MAX = 13.5` (estrelas mais brilhantes que T ~9 já foram muito estudadas; acima de 13,5 o QLP não cobre).
  - `contratio` do TIC < 0,2 (fração do fluxo vinda de vizinhas, já calculada pelo TIC).
- Primeira rodada: limitar a `ALVO_MAX = 500` estrelas.

Campo inicial sugerido: um setor que cruze o plano da Via Láctea. Há mais estrelas e menos atenção individual. O custo é mais contaminação, tratada na Fase 6.

## 6. Fase 3: baixar curvas

- `lightkurve.search_lightcurve(tic, sector=..., author=...)`. Confirmar na primeira busca real qual string de `author` corresponde a TESS-SPOC FFI (aparece na coluna `author` do resultado).
- Usar o fluxo corrigido (`KSPSAP_FLUX` no QLP, `PDCSAP_FLUX` no SPOC), remover pontos com `quality != 0`, normalizar.
- Cache em disco (`data/curvas/<tic>_s<setor>.fits`) para não baixar duas vezes.
- Retry com `time.sleep` nas chamadas ao MAST, como no Rastro.

## 7. Fase 4: detectar sinal

Duas buscas por estrela:

- **Lomb-Scargle** (variáveis senoidais: pulsantes, rotação, binárias de contato). Guarda período, potência máxima e FAP (probabilidade de alarme falso).
- **BLS** (eclipses e trânsitos em formato de caixa). Guarda período, profundidade, duração, SNR.

Métricas gravadas em `sinais`: `tic`, `setor`, `metodo`, `periodo_d`, `amplitude`, `potencia`, `fap` ou `snr`, `n_ciclos`.

Cortes para virar sinal:

- `LS_FAP_MAX = 1e-4` ou `BLS_SNR_MIN = 10`.
- Pelo menos 3 ciclos completos no setor (`periodo_d < ~9 d` num setor de ~27 d).
- Descartar períodos próximos de sistemáticos conhecidos do TESS: ~13,7 d (órbita do satélite), seus harmônicos, e ~1 d.
- Amplitude acima de 3x o ruído ponto a ponto.

## 8. Fase 5: cruzar com conhecidos

Cone search de raio `RAIO_MATCH_ARCSEC = 30` (o pixel do TESS tem 21"; uma variável conhecida a 1 pixel pode ser a fonte real do sinal). Catálogos, todos via VizieR ou serviço próprio:

| Catálogo | Acesso | O que pega |
|---|---|---|
| VSX (AAVSO) | VizieR `B/vsx` | Todas as variáveis catalogadas; é o filtro que o moderador do VSX vai usar |
| TESS-EBs (Prša et al. 2022) | VizieR `J/ApJS/258/16` | 4584 binárias eclipsantes dos setores 1 a 26 |
| Gaia DR3 variabilidade | VizieR `I/358` (tabelas de classificação e de binárias eclipsantes) | Mais de 2 milhões de binárias eclipsantes candidatas e outras classes |
| ASAS-SN variáveis | VizieR | Variáveis brilhantes do céu todo |
| ZTF variáveis periódicas (Chen et al. 2020) | VizieR `J/ApJS/249/18` | Variáveis do hemisfério norte, até mag ~20 |
| ATLAS variáveis candidatas (Heinze et al. 2018) | VizieR `J/AJ/156/241` | 4,7 milhões de candidatas do céu ao norte de Dec -30° |
| Variáveis periódicas do TESS, SPB do TESS, rotação do TIC | VizieR `J/ApJS/276/57`, `J/ApJS/268/16`, `J/AJ/155/39/table6` | Catálogos recentes que o VSX ainda não absorveu |
| Gaia DR2 grande amplitude | VizieR `J/A+A/648/A44` | Variáveis de grande amplitude, sem período |
| TOI (candidatos a planeta) | CSV do ExoFOP | Sinais já investigados pela missão TESS |
| SIMBAD | `astroquery.simbad` | Literatura em geral |

Os identificadores VizieR exatos das tabelas Gaia DR3 e ASAS-SN precisam ser confirmados na implementação.

Status gravado: `conhecido` (match com período compatível), `conhecido_vizinho` (match a mais de 10" mas dentro do raio), `novo`.

Um match no Gaia DR3 como "candidata a binária eclipsante" não impede a submissão ao VSX, mas reduz o mérito. Registrar à parte (`gaia_candidata=True`).

## 9. Fase 6: checar contaminação

O maior risco de falso positivo no TESS é a vizinha: uma estrela variável próxima espalha luz no pixel da estrela-alvo, e o sinal parece ser dela.

- Listar fontes Gaia DR3 num raio de 2 pixels (~42") com diferença de magnitude < 4.
- Se alguma vizinha for variável conhecida (Fase 5 já cobre), descartar.
- Se a vizinha for brilhante o bastante para gerar a amplitude observada, marcar `suspeito_blend`.
- Persistência: se a estrela foi observada em outro setor, o sinal precisa reaparecer com o mesmo período.
- Opcional, para os finalistas: baixar o TPF/recorte FFI (`lightkurve.search_tesscut`) e verificar em qual pixel o sinal é mais forte (centróide).

## 10. Fase 7: triagem

Para cada candidato, gerar uma figura com: curva bruta, curva dobrada em fase, periodograma, imagem do campo com vizinhas Gaia marcadas.

- Revisão humana é o veredito. A LLM (reaproveitando o módulo `llm_triage` do Rastro, OpenAI-compatible) só prioriza: classifica o tipo provável (EA, EB, EW, pulsante, rotacional) e aponta sinais de sistemático.
- Saída: `candidatos_fase7` com `tipo_provavel`, `nota_llm`, `revisao_humana` (`confirmar`/`descartar`).

## 11. Fase 8 e submissão ao VSX

O moderador do VSX confere três coisas: o objeto está identificado corretamente, é variável e é desconhecido. O VSX não tem API de submissão: o envio é pelo formulário do site, e na primeira vez a AAVSO recomenda o **New Star Wizard**, que guia campo a campo. A fila de moderação é longa; conte com semanas.

`python src/ficha_vsx.py` gera `data/vsx/fichas.md` (um bloco por estrela, com os campos do formulário), `fichas.csv` e a curva em fase `<tic>_fase.png`. Checklist por estrela (marcado o que o pipeline já entrega):

1. **Revisão visual concluída** no app: decisão `confirmado` em `revisao_humana`. *(app)*
2. **Período certo, não um harmônico.** Binária eclipsante costuma sair no LS com metade do período real: a figura da Fase 7 mostra a curva dobrada em P e em 2P; escolher o que separa os dois eclipses. *(Fase 8 sugere P ou 2P: 2P quando, dobrada em 2P, a curva mostra eclipses estreitos com brilho plano ou mínimos de profundidades diferentes; conferir na curva em fase)*
3. **Persistência:** o sinal reaparece em outros setores com o mesmo período. *(Fase 6)*
4. **Fonte certa no pixel:** o mapa por pixel da Fase 7 tem o pico no alvo, e não há vizinha Gaia brilhante capaz de gerar a amplitude (`suspeito_blend` falso). O fórum da AAVSO cita a contaminação por vizinhas como o principal cuidado com TESS. *(Fases 6 e 7)*
5. **Ainda desconhecido, conferido de novo na véspera:** VSX, SIMBAD e VizieR em geral (não só os catálogos da Fase 5), incluindo ATLAS (ATO), Gaia DR3, ZTF, Pan-STARRS e CSS. Os moderadores avisam que VSX e SIMBAD sozinhos não garantem que o objeto é novo. Entrada marcada como "dubious" no ATO pode ser reivindicada. *(Fase 8 consulta o VizieR inteiro a 30" e lista os catálogos de variáveis; abrir cada um e ver se é a mesma estrela e o mesmo período)*
6. **Identificação e posição** pela fonte Gaia DR3 correspondente (ID e coordenadas). *(Fase 8: fonte mais brilhante a até 3")*
7. **Tipo de variável** pela nomenclatura do VSX (EA, EB, EW, ROT, DSCT, etc.; PDF de tipos no site do VSX). Tipo espectral não é obrigatório. *(Fase 8 sugere EA, EB ou "ROT, EW ou pulsante"; a palavra final é humana)*
8. **Período e época:** período em dias e instante de mínimo (eclipse) ou máximo (pulsante) em BJD; no TESS, BJD = BTJD + 2457000. *(Fase 8: período sugerido e época do mínimo)*
9. **Faixa de magnitude:** magnitude média V de catálogo (derivada do Gaia DR3) no campo de máximo e a amplitude TESS no de mínimo, com "Minimum is an amplitude" marcado e "TESS" no campo de banda personalizada. Se a amplitude for grande o bastante para ZTF ou ASAS-SN, a AAVSO prefere combinar com esses dados e usar as magnitudes padrão deles. *(Fase 8: V pela relação G, BP-RP de Riello+2021 e amplitude pico a pico na curva dobrada em 200 bins, que não dilui eclipse estreito; avisa quando a amplitude passa de 0,05 mag)*
10. **Evidência anexada:** curva em fase (obrigatória para variável periódica) e curva no tempo, feitas por você. O manual avisa que não basta apontar uma curva que qualquer um acha nos bancos de dados. *(Fase 8: curva em fase; Fase 7: figura completa)*
11. **Nome provisório**, se quiser: o VSX aceita designação própria (ex.: "VGL V1"). *(manual)*

Risco que segue em aberto: a AAVSO não diz explicitamente se dados só do TESS bastam. O formato que ela recomenda para TESS (item 9) indica que sim, mas pede cautela com dados escassos e sugere combinar levantamentos. Para as candidatas com amplitude acima de ~0,05 mag, juntar a curva ZTF reduz esse risco.

Fontes: fórum da AAVSO ("How to: VSX and variable star discovery", "Passband for TESS data") e o manual de submissão do VSX (aavso.org/vsx).

## 12. Teste: LLM com visão classifica o tipo da variável?

**Pergunta.** Uma LLM que lê imagens consegue fazer o passo humano da Fase 8 (tipo da variável e escolha entre P e 2P) olhando a curva em fase? Se sim, a mesma técnica serviria para procurar curvas que não se encaixam em tipo nenhum (objetos não classificados).

**Método** (`tools/teste_llm_visao.py`). Gabarito: estrelas do VSX com tipo firme (sem ":"), período de 0,1 a 13 d e V de 8 a 13,5, num raio de 5° do campo do setor 55; até 12 por classe (EA, EB, EW, ROT, DSCT, RR). Para cada uma: TIC pelo VizieR, curva QLP do setor mais perto do 55, dobra num período de referência sorteado entre o verdadeiro e a metade (o erro típico do LS), figura com dois painéis (A em P, B em 2P). A LLM responde tipo e painel; a heurística `sugerir` da Fase 8 responde o mesmo, como base. Resultados em `data/teste_llm/resultados_<modelo>.csv`, gravados a cada estrela; o script retoma de onde parou.

**Resultado (2026-10-19, plano grátis do Gemini):**

| Modelo | Estrelas | Tipo certo | Painel certo (LLM) | Painel certo (heurística) |
|---|---|---|---|---|
| gemini-2.5-flash | 22 (12 DSCT, 10 EA) | 23% | 55% | não medido |
| gemini-2.5-flash-lite | 18 (12 DSCT, 6 EA) | 44% (EA 6/6, DSCT 2/12) | 44% | 94% |

As figuras foram conferidas a olho e estão boas. Os erros são do modelo: uma senoide limpa de 0,145 d, que no painel B aparece como dois ciclos iguais, foi lida como "dois mínimos distintos, binária EA". Parte do erro em EA também vem do gabarito: várias "EA" do VSX têm brilho curvo entre os eclipses e seriam defensáveis como EB.

**Conclusão.** Com os modelos grátis de hoje, a LLM com visão não serve para isso: erra o tipo na maioria das vezes e escolhe o período pior que o acaso, enquanto a heurística numérica acerta o período em 94%. A ideia de procurar objetos não classificados com LLM fica parada até haver um modelo melhor e acessível. Para repetir com outro modelo: `python -u tools/teste_llm_visao.py --modelo <modelo>` (OpenAI-compatible; `LLM_VISAO_*` em `config.py`).

**Limites do teste.** Amostra pequena e só de duas classes, porque o plano grátis do Gemini dá cerca de 20 pedidos por dia por modelo; `gemini-3.8-flash` estava sobrecarregado (503), o modelo com visão do Groq saiu do plano grátis, o GLM com visão não está no plano da Z.ai e o Gemma 3 deixou de ser grátis no OpenRouter.

## 13. Riscos conhecidos

- **Contaminação por vizinha:** principal fonte de falso positivo (Fase 6).
- **Sistemáticos do TESS:** luz espalhada, descarga de momento angular, órbita de 13,7 d (cortes da Fase 4).
- **Harmônicos:** binária eclipsante com eclipses iguais aparece com metade do período real. A triagem deve testar 2x o período.
- **Volume:** a maioria dos sinais será conhecida ou espúria. Isso é esperado e serve de validação.

## 14. Próximos passos

1. Revisar no app as 9 candidatas do setor 55 (`streamlit run app/revisao.py`).
2. Para as confirmadas, gerar as fichas (`python src/ficha_vsx.py`) e conferir cada item do checklist da seção 11.
3. Criar a conta na AAVSO e submeter a primeira pelo New Star Wizard.
4. Depois da primeira aceita, varrer outros setores (mudar `ALVO_SETOR` e o campo em `config.py`).
