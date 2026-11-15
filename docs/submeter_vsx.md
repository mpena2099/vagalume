# Como submeter uma candidata ao VSX

O VSX (The International Variable Star Index) é o catálogo de estrelas variáveis da AAVSO. A submissão é feita à mão, pelo site [vsx.aavso.org](https://vsx.aavso.org): não há envio automático. Um moderador confere três coisas: a estrela está identificada certo, é variável e ainda não era conhecida. Conte com semanas até a resposta.

Faça uma estrela por vez. Pelas regras do VSX, usuário novo só pode ter **uma submissão** até a primeira ser aprovada, e depois o limite é de 5 por semana. Submissão que fica 60 dias como rascunho, ou à espera de uma correção pedida pelo moderador, é apagada.

## 1. Antes de abrir o formulário

Na página **Fichas** do app, para a estrela escolhida (a página já confere o VSX sozinha pelas coordenadas, guarda o tipo que você escolher, gera o comentário em inglês e baixa os anexos):

1. **Leia os avisos da ficha.** Aviso que diz "Não submeta" impede o envio. Aviso que diz "Pode submeter" é só informativo: com o VizieR do CDS fora do ar, a busca a 30" foi feita nos 25 principais catálogos de variáveis (VSX, GCVS, Gaia DR3, ATLAS, ASAS-SN e outros) em vez de nos milhares do VizieR inteiro. A checagem que evita enviar estrela já submetida é a do próprio VSX, que fica em outro servidor e a página faz ao vivo; o moderador confere de novo antes de aceitar.
2. **Decida o tipo.** Quando a curva admite mais de um tipo ("ROT, EW ou pulsante"), a Fase 8 só sugere um se houver evidência direta: o período, a forma da curva dobrada em 2P (dois mínimos iguais e curva contínua indicam EW; onda única, ROT ou pulsante) e a temperatura da estrela no Gaia DR3 (Teff do GSP-Phot, ou do `I/355/paramp`). Exemplos: P menor que 0,25 d e Teff acima de 6500 K, DSCT; Teff acima de 10000 K e P entre 0,3 e 3 d, SPB; Teff entre 6800 e 7800 K e P entre 0,3 e 3 d, GDOR; Teff abaixo de 6000 K, onda única e P acima de 0,5 d, ROT; EW com mínimos iguais em 2P, 2P entre 0,2 e 1 d e Teff entre 4000 e 7000 K. Se duas regras valem juntas, se a Teff não existe ou se nenhuma regra serve, a ficha não sugere nada. Com sugestão, a página abre o tipo provável já escolhido e pede só que você o confirme (botão "Confirmar o tipo provável", depois de olhar a curva em fase). Sem sugestão, escolha pela forma da curva; na dúvida, prefira a estrela seguinte e deixe essa para depois.
3. **Confira o período.** A Fase 8 mede o instante do mínimo em cada setor usado e ajusta uma reta T = T0 + n·P (O-C). Se o maior desvio é menor que 0,02 em fase, o alerta some e a ficha traz o período, o erro e a época desse ajuste. Se não, o alerta "períodos dos setores não alinham" traz o O-C de cada setor: abra a figura e veja se os mínimos de setores diferentes caem no mesmo lugar. Se não caem, o período ainda não está bom para enviar. Com um setor só não há o que conferir.
   Antes do O-C, a Fase 8 compara a profundidade dos eclipses de ciclo par e de ciclo ímpar (largura medida na própria curva, erro da mediana de cada lado). Se a diferença passa de 3 sigmas no conjunto e tem o mesmo sinal em todo setor com eclipses suficientes, o período medido era metade do orbital: a ficha usa 2P, com a época no mínimo mais fundo, e refaz O-C, amplitude e figura. A página Fichas mostra "Eclipses pares e ímpares iguais" ou "Período dobrado: eclipses pares e ímpares diferem N σ", e o comentário em inglês cita as profundidades. Com poucos eclipses a ficha avisa que não há decisão: confira na figura se os dois mínimos têm a mesma profundidade.
4. **Veja a vizinha.** A ficha diz se o blend está resolvido (pico no alvo e vizinha a mais de 1 pixel), se o sinal parece da vizinha ou se ficou para você conferir (explicação logo abaixo). Nos dois últimos casos, abra o painel "Mapa por pixel e curvas da triagem".
5. **Busque no VSX online.** A página Fichas faz isso sozinha e lista o que achar; para conferir à mão, em [vsx.aavso.org](https://vsx.aavso.org), use a busca por coordenadas com a RA e a Dec da ficha e raio de 1 minuto de arco. Se a estrela já aparece, alguém submeteu antes: não envie.

### O que é suspeita de blend

Os pixels do TESS são grandes: cada um cobre 21" do céu. A luz das estrelas próximas cai nos mesmos pixels e se soma à do alvo, de modo que, se uma vizinha varia, a curva do alvo também parece variar. Isso é um blend (mistura).

A Fase 6 faz uma conta para cada vizinha do Gaia a até 42" (dois pixels) com até 4 magnitudes a menos que o alvo: quanto ela precisaria variar para produzir sozinha a variação observada? Se bastar menos de 50% do brilho dela, uma estrela real consegue, e a ficha sai com "suspeito de blend". Se precisasse de mais, a vizinha não explica o sinal.

É uma suspeita, e a Fase 8 a resolve sozinha com o deslocamento do pico do mapa por pixel (a distância do pico ao alvo, em pixels, que a triagem guarda) e a distância de cada vizinha suspeita (o Gaia dá a separação e a diferença de magnitude):

- **Pico no pixel do alvo (a menos de 1 pixel) e vizinha suspeita a mais de 1 pixel (21"):** resolvido, a variação é da sua estrela. A ficha diz "pico no alvo; vizinha a N" não explica o sinal". Mencione a vizinha no comentário (a frase em inglês gerada pela página já faz isso).
- **Pico deslocado de 1 pixel ou mais, a uma distância compatível com a de uma vizinha (diferença de até 1 pixel):** o sinal parece dela. A página bloqueia o envio. Não submeta.
- **Vizinha a menos de 1 pixel do alvo, pico deslocado que não bate com nenhuma vizinha ou vizinhas que o Gaia não respondeu:** fica como atenção. O pixel não separa as duas estrelas, então olhe o mapa por pixel; se não der para distinguir, deixe a estrela para depois e comece pelas outras.

Só há a distância do pico, não a direção, por isso "compatível" quer dizer que o pico está tão longe do alvo quanto a vizinha. Na ficha o resultado fica em `blend_veredito` e `blend_motivo`.

## 2. Criar o login no VSX

1. Em [vsx.aavso.org](https://vsx.aavso.org), clique em **Register** no menu do topo.
2. Preencha o formulário (o nome de login tem de 6 a 12 caracteres) e clique em **Register**.
3. Abra o e-mail de confirmação e clique no link: o login só funciona depois disso.

O login do VSX é separado da conta do site da AAVSO.

## 3. Abrir o formulário

1. Clique em **Log In** e entre.
2. Clique em **Submit** no menu do topo.
3. Escolha o **New Star Wizard**. Ele pede os campos um de cada vez e explica cada um. O **New Star Form** pede os mesmos dados numa página só; use-o quando já conhecer o caminho.
4. Marque **Draft only** (no fim do formulário) até conferir tudo: o rascunho fica salvo e pode ser editado. Use também o link **Spot check** do campo de posição e o **Check name** do nome, que procuram duplicatas no próprio VSX.

## 4. Copiar os campos da ficha

Cada campo da página Fichas tem um botão de copiar, e o comentário em inglês já vem pronto com os números da ficha (confira antes de colar). Os anexos têm botão de baixar na própria página. Os nomes no formulário podem variar um pouco; a correspondência é esta:

| No formulário do VSX | Da ficha |
|---|---|
| Nome e identificadores | "Outros nomes": o TIC e o Gaia DR3. Se quiser, dê um nome provisório seu (ex.: "VGL V1") |
| Coordenadas (RA, Dec) | "RA (Gaia DR3)" e "Dec (Gaia DR3)", em graus |
| Tipo de variável | O tipo que você decidiu no passo 1 (EA, EB, EW, ROT...) |
| Período | "Período (d)" |
| Época | "Época do mínimo (BJD)". O VSX fala em HJD, mas aceita o BJD_TDB do TESS (a diferença é de cerca de um minuto); o comentário avisa isso |
| Magnitude máxima | "Magnitude V (máxima)", na banda V |
| Magnitude mínima | "Amplitude (mag, TESS)": marque **"Minimum is an amplitude"** e escreva **TESS** no campo de banda |
| Fonte dos dados | "TESS QLP (FFI)" e os setores da ficha. O guia do VSX recomenda o PDCSAP, que é do SPOC; para estrela observada só nas imagens completas (FFI), o QLP é o produto disponível |
| Anexos | A curva em fase `data/vsx/<tic>_fase.png` (obrigatória) e a figura da triagem `data/triagem/<tic>.png`. Mande as duas: o VSX avisa que a abertura do TESS junta luz de vizinhas até ~120", e o mapa por pixel da triagem é a prova de que o sinal vem do alvo |

O comentário em inglês gerado pela página diz como a estrela foi achada (TESS QLP e setores), o período medido com todos os setores (e por que é 2P, quando os eclipses pares e ímpares diferem), a época em BJD_TDB, a amplitude, que a variação fica abaixo da precisão do ASAS-SN e do ZTF quando é o caso (o VSX incentiva combinar com levantamentos de solo), o que as buscas no VSX e no VizieR acharam e, se houver, a vizinha e o que o mapa por pixel mostra.

## 5. Depois de enviar

1. No app, página **Fichas**, marque **Enviada ao VSX** na estrela.
2. O moderador responde por e-mail ou pelo próprio VSX. Se ele pedir ajuste, corrija e responda.
3. O aceite é marcado sozinho: ao abrir a página **Fichas**, o app consulta o VSX para cada estrela enviada e ainda não aceita. Quando aparece um objeto a até 10" da posição Gaia da ficha, a estrela vira **Aceita no VSX**, o nome que ela recebeu é preenchido e o app avisa "TIC X aceita no VSX como NOME". Se o VSX estiver fora do ar, marque à mão.

Os detalhes de cada item (P ou 2P, faixa de magnitude, por que a amplitude do TESS) estão no checklist da seção 11 da [especificação](../especificacao.md).
