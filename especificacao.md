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

A Fase 8 (submissão ao VSX) é manual, guiada por checklist (seção 11).

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

## 11. Submissão ao VSX (manual)

Pelo que a AAVSO publica, o moderador confere três coisas: o objeto está identificado corretamente, é variável e é desconhecido. Checklist:

1. Conta no site da AAVSO.
2. Verificar de novo no VSX, VizieR e SIMBAD que o objeto é novo.
3. Posição e identificação pela fonte Gaia DR3 correspondente.
4. Tipo de variável pela nomenclatura do VSX (ver o PDF de tipos no site do VSX).
5. Período e época (instante de mínimo ou máximo em BJD).
6. Faixa de magnitude: a AAVSO recomenda usar a magnitude média V de catálogo (ex.: Gaia DR3) como máximo e a amplitude TESS no campo de mínimo, marcando "Minimum is an amplitude". A banda "TESS" vai no campo de banda personalizada.
7. Anexar a curva de luz e a curva em fase como evidência.

Pontos em aberto, a confirmar no manual atual de submissão do VSX antes da primeira submissão:

- Se dados só do TESS bastam ou se o moderador pede confirmação com outros dados. Um post antigo do fórum dizia que dados espaciais precisavam de observação própria de confirmação; não está claro se a regra continua. Se continuar, as curvas ZTF ou ASAS-SN públicas do mesmo objeto podem servir de segunda fonte.
- Campos obrigatórios exatos do formulário.

## 12. Riscos conhecidos

- **Contaminação por vizinha:** principal fonte de falso positivo (Fase 6).
- **Sistemáticos do TESS:** luz espalhada, descarga de momento angular, órbita de 13,7 d (cortes da Fase 4).
- **Harmônicos:** binária eclipsante com eclipses iguais aparece com metade do período real. A triagem deve testar 2x o período.
- **Volume:** a maioria dos sinais será conhecida ou espúria. Isso é esperado e serve de validação.

## 13. Próximos passos

1. Criar repositório, `config.py`, `requirements.txt`.
2. Implementar a Fase 1 e passar.
3. Implementar Fases 2 a 5 e rodar em 500 estrelas de um setor.
4. Medir quantos sinais batem com catálogos (recall, como planejado no Rastro).
5. Fases 6 e 7, revisar candidatos, submeter o primeiro.
