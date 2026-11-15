# Como submeter uma candidata ao VSX

O VSX (The International Variable Star Index) é o catálogo de estrelas variáveis da AAVSO. A submissão é feita à mão, pelo site [vsx.aavso.org](https://vsx.aavso.org): não há envio automático. Um moderador confere três coisas: a estrela está identificada certo, é variável e ainda não era conhecida. Conte com semanas até a resposta.

Faça uma estrela por vez. Pelas regras do VSX, usuário novo só pode ter **uma submissão** até a primeira ser aprovada, e depois o limite é de 5 por semana. Submissão que fica 60 dias como rascunho, ou à espera de uma correção pedida pelo moderador, é apagada.

## 1. Antes de abrir o formulário

Na página **Fichas** do app, para a estrela escolhida (a página já confere o VSX sozinha pelas coordenadas, guarda o tipo que você escolher, gera o comentário em inglês e baixa os anexos)).

A página dá o veredito: **"Pode enviar"**, com a lista do que foi conferido, ou **"Ainda não envie"**, com o próximo passo. Ela confere a ficha, o VSX ao vivo, os anexos e o limite de submissões do VSX (enquanto a primeira não for aceita, as outras ficam em "Aguardar o VSX"). Na tabela, "Pronta" quer dizer o mesmo que "Pode enviar", só sem a consulta ao VSX, que é feita ao abrir a estrela. Os itens abaixo explicam o que ela confere:

1. **Leia os avisos da ficha.** Aviso que diz "Não submeta" impede o envio. Aviso que diz "Pode submeter" é só informativo: com o VizieR do CDS fora do ar, a busca a 30" foi feita nos 25 principais catálogos de variáveis (VSX, GCVS, Gaia DR3, ATLAS, ASAS-SN e outros) em vez de nos milhares do VizieR inteiro. A checagem que evita enviar estrela já submetida é a do próprio VSX, que fica em outro servidor e a página faz ao vivo; o moderador confere de novo antes de aceitar.
2. **Decida o tipo.** Quando a curva admite mais de um tipo ("ROT, EW ou pulsante"), a Fase 8 só sugere um se houver evidência direta: o período, a forma da curva dobrada em 2P (dois mínimos iguais e curva contínua indicam EW; onda única, ROT ou pulsante) e a temperatura da estrela no Gaia DR3 (Teff do GSP-Phot, ou do `I/355/paramp`). Exemplos: P entre 0,01 e 0,2 d e Teff acima de 6500 K, DSCT; Teff acima de 10000 K e P entre 0,4 e 5 d, SPB; Teff entre 6300 e 7800 K e P entre 0,25 e 4 d, GDOR (as faixas de período e de tipo espectral são as da definição de cada tipo no VSX); Teff abaixo de 6000 K, onda única e P acima de 0,5 d, ROT; EW com mínimos iguais em 2P, 2P entre 0,2 e 1 d e Teff entre 4000 e 7000 K. Se duas regras valem juntas, se a Teff não existe ou se nenhuma regra serve, a ficha não sugere nada. Com sugestão, a página abre o tipo provável já escolhido e pede só que você o confirme (botão "Confirmar o tipo provável", depois de olhar a curva em fase). Sem sugestão, escolha pela forma da curva (veja [Os tipos de variável](#os-tipos-de-variável)); na dúvida, prefira a estrela seguinte e deixe essa para depois.
3. **Confira o período.** A Fase 8 mede o instante do mínimo em cada setor usado e ajusta uma reta T = T0 + n·P (O-C). Se o maior desvio é menor que 0,02 em fase, o alerta some e a ficha traz o período, o erro e a época desse ajuste. Se não, o alerta "períodos dos setores não alinham" traz o O-C de cada setor: abra a figura e veja se os mínimos de setores diferentes caem no mesmo lugar. Se não caem, o período ainda não está bom para enviar. Com um setor só não há o que conferir.
   Antes do O-C, a Fase 8 compara a profundidade dos eclipses de ciclo par e de ciclo ímpar (largura medida na própria curva, erro da mediana de cada lado). Se a diferença passa de 3 sigmas no conjunto e tem o mesmo sinal em todo setor com eclipses suficientes, o período medido era metade do orbital: a ficha usa 2P, com a época no mínimo mais fundo, e refaz O-C, amplitude e figura. A página Fichas mostra "Eclipses pares e ímpares iguais" ou "Período dobrado: eclipses pares e ímpares diferem N σ", e o comentário em inglês cita as profundidades. Com poucos eclipses a ficha avisa que não há decisão: confira na figura se os dois mínimos têm a mesma profundidade.
4. **Veja a vizinha.** A ficha diz se o blend está resolvido (pico no alvo e vizinha a mais de 1 pixel), se o sinal parece da vizinha ou se ficou para você conferir (explicação logo abaixo). Nos dois últimos casos, abra o painel "Mapa por pixel e curvas da triagem".
5. **Busque no VSX online.** A página Fichas faz isso sozinha e lista o que achar; para conferir à mão, em [vsx.aavso.org](https://vsx.aavso.org), use a busca por coordenadas com a RA e a Dec da ficha e raio de 2 minutos de arco. Se a estrela já aparece, alguém submeteu antes: não envie. A página usa o mesmo raio do Spot Check do formulário (120"), e cada variável que ele lista aparece na página com o veredito: a até 30" é a mesma estrela (não envie); com o mesmo período, o sinal pode ser dela (não envie); de 30" a 60", confira; além de 60" (3 pixels do TESS) e com período diferente, é outra estrela, e o comentário em inglês já a cita ao moderador.

### O que é suspeita de blend

Os pixels do TESS são grandes: cada um cobre 21" do céu. A luz das estrelas próximas cai nos mesmos pixels e se soma à do alvo, de modo que, se uma vizinha varia, a curva do alvo também parece variar. Isso é um blend (mistura).

A Fase 6 faz uma conta para cada vizinha do Gaia a até 42" (dois pixels) com até 4 magnitudes a menos que o alvo: quanto ela precisaria variar para produzir sozinha a variação observada? Se bastar menos de 50% do brilho dela, uma estrela real consegue, e a ficha sai com "suspeito de blend". Se precisasse de mais, a vizinha não explica o sinal.

É uma suspeita, e a Fase 8 a resolve sozinha com o deslocamento do pico do mapa por pixel (a distância do pico ao alvo, em pixels, que a triagem guarda) e a distância de cada vizinha suspeita (o Gaia dá a separação e a diferença de magnitude):

- **Pico no pixel do alvo (a menos de 1 pixel) e vizinha suspeita a mais de 1 pixel (21"):** resolvido, a variação é da sua estrela. A ficha diz "pico no alvo; vizinha a N" não explica o sinal". Mencione a vizinha no comentário (a frase em inglês gerada pela página já faz isso).
- **Pico deslocado de 1 pixel ou mais, a uma distância compatível com a de uma vizinha (diferença de até 1 pixel):** o sinal parece dela. A página bloqueia o envio. Não submeta.
- **Vizinha a menos de 1 pixel do alvo, pico deslocado que não bate com nenhuma vizinha ou vizinhas que o Gaia não respondeu:** fica como atenção. O pixel não separa as duas estrelas, então olhe o mapa por pixel; se não der para distinguir, deixe a estrela para depois e comece pelas outras.

Só há a distância do pico, não a direção, por isso "compatível" quer dizer que o pico está tão longe do alvo quanto a vizinha. Na ficha o resultado fica em `blend_veredito` e `blend_motivo`.

### Os tipos de variável

O VSX classifica cada estrela por uma sigla. A lista completa, com a definição de cada uma, está em [Variable star type designations in VSX](https://vsx.aavso.org/index.php?view=about.vartypes); abaixo estão as que o Vagalume encontra, com os valores dessa lista e o que reconhecer na curva em fase.

**Binárias eclipsantes.** Duas estrelas em órbita; a luz cai quando uma passa na frente da outra. O período é o da órbita, com dois eclipses por volta (às vezes o segundo é raso demais para ver).

| Sigla | Nome | Como é a curva | Período | Amplitude |
|---|---|---|---|---|
| EA | Algol (β Persei) | Dá para marcar o início e o fim de cada eclipse; entre eles a luz fica quase constante. O mínimo secundário pode faltar | de 0,2 a mais de 10000 d | de centésimos a várias mag |
| EB | β Lyrae | Varia o tempo todo entre os eclipses (estrelas deformadas); o mínimo secundário sempre aparece e costuma ser bem mais raso que o primário. Estrelas quentes (tipos B e A) | em geral acima de 0,5 d | menos de 2 mag em V |
| EW | W Ursae Majoris | Varia o tempo todo, com os dois mínimos quase iguais: as estrelas quase se tocam. Tipos F, G e mais frios | em geral abaixo de 1 d | menos de 0,8 mag em V |
| ELL | Elipsoidal | Onda suave com dois máximos e dois mínimos por órbita, sem eclipse: a estrela deformada mostra mais ou menos área | o da órbita | até 0,1 mag (raramente 0,3) |

**Rotação.** Uma mancha na superfície entra e sai de vista conforme a estrela gira. O período é o da rotação.

| Sigla | Nome | Como é a curva | Período | Amplitude |
|---|---|---|---|---|
| ROT | Rotacional | Mancha numa estrela que não se encaixa num tipo mais específico. Uma onda por período, que muda de forma de um setor para outro (as manchas mudam) | de fração de dia a dezenas de dias | pequena |
| BY | BY Draconis | Como a ROT, em anã fria com linhas de emissão (dKe a dMe), às vezes com flares | de fração de dia a 120 d | de centésimos a 0,5 mag em V |

**Pulsantes.** A própria estrela incha e encolhe.

| Sigla | Nome | Como é a curva | Período | Amplitude |
|---|---|---|---|---|
| DSCT | δ Scuti | Ciclos curtos, muitas vezes com várias frequências; estrela A0 a F5. Acima de 0,15 mag e curva assimétrica vira HADS | de 0,01 a 0,2 d | de 0,003 a 0,9 mag em V |
| GDOR | γ Doradus | Pulsação lenta, com uma ou várias frequências, em anã A7 a F7 (~6300 a 7800 K) | de 0,25 a 4 d | em geral até 0,1 mag |
| SPB | B de pulsação lenta | Uma ou várias frequências, em estrela B2 a B9 (acima de ~10000 K) | de 0,4 a 5 d | menos de 0,1 mag |
| RRAB | RR Lyrae ab | Subida brusca e descida lenta | de 0,3 a 1 d | de 0,5 a 2 mag em V |
| RRC | RR Lyrae c | Quase simétrica, às vezes senoidal | de 0,16 a 0,5 d | até 0,8 mag em V |
| CEP | Cefeida | Supergigante (classe Ib ou II); como a RRAB, mas lenta | de 1 a 135 d | de centésimos a 2 mag em V |

**Sem tipo definido.** `VAR` é variável de tipo não especificado, usada para variável suspeita que ainda não foi estudada a fundo. O formulário pede `*` quando o tipo é desconhecido, com a explicação no campo de observações (Remarks); na lista do VSX, `*` também é o tipo de estrelas únicas, fora de qualquer classe.

**Como escrever a dúvida.** O VSX tem uma notação para isso, que vai no campo **Customized type** do formulário (ele tem precedência sobre o menu):

- `:` depois do tipo: classificação incerta (`EA:`). É o mesmo que marcar **Uncertain**.
- `|` entre dois tipos: um ou outro (`ROT|EW`). Use quando a curva admite os dois e a página não decidiu. Exemplo da própria lista: `ELL|DSCT`, uma elipsoidal ou uma DSCT com metade do período.
- `+` entre dois tipos: os dois juntos na mesma estrela (`EA+DSCT`, uma binária eclipsante com uma componente pulsante).
- `/` depois do tipo: subtipo (`EA/DM`, binária destacada de duas anãs). Não é preciso informar subtipo.

A confusão mais comum é entre P e 2P. Uma EW medida pelo Lomb-Scargle aparece com metade do período (os dois mínimos iguais viram um só), e uma ROT ou pulsante pode parecer EW se for dobrada em 2P. A curva em 2P, a Teff do Gaia e a forma dos mínimos decidem; a Fase 8 faz essa conta e sugere o tipo provável. Se ainda restar dúvida entre dois tipos, use `|` em vez de escolher um no chute.

## 2. Criar o login no VSX

1. Em [vsx.aavso.org](https://vsx.aavso.org), clique em **Register** no menu do topo.
2. Preencha o formulário (o nome de login tem de 6 a 12 caracteres) e clique em **Register**. O nome vai nos créditos da descoberta: em **Given name**, o primeiro nome com as iniciais do meio (ex.: "Maria S."); em **Family name**, o último sobrenome ("Silva"). Escreva sem acentos, como em publicações astronômicas, e use sempre a mesma forma.
3. Abra o e-mail de confirmação e clique no link: o login só funciona depois disso.

O login do VSX é separado da conta do site da AAVSO.

## 3. Abrir o formulário

1. Clique em **Log In** e entre.
2. Clique em **Submit** no menu do topo.
3. Na pergunta "Do you want to submit a new variable star based on your observations only?", responda **não** e não marque **Novice discovery**: essa opção é para quem achou a estrela na própria fotometria, e a do Vagalume vem da análise de dados de levantamento (TESS) em vários setores.
4. Escolha o **New Star Wizard**. Ele pede os campos um de cada vez e explica cada um. O **New Star Form** pede os mesmos dados numa página só; use-o quando já conhecer o caminho.
5. Marque **Draft only** (no fim do formulário) até conferir tudo: o rascunho fica salvo e pode ser editado. Use também o link **Spot check** do campo de posição e o **Check name** do nome, que procuram duplicatas no próprio VSX.

## 4. Copiar os campos da ficha

Cada campo da página Fichas tem um botão de copiar, e o comentário em inglês já vem pronto com os números da ficha (confira antes de colar). Os anexos têm botão de baixar na própria página. Os nomes no formulário podem variar um pouco; a correspondência é esta:

| No formulário do VSX | Da ficha |
|---|---|
| Primary name e Other names | "Nome principal" (o TIC, porque a estrela foi achada no banco do TESS; depois clique em **Check name**) e "Outros nomes" (Gaia DR3, 2MASS, UCAC4, WISEA e, se houver, TYC e HIP, tirados do catálogo TIC do MAST, um por linha e no formato do Dictionary of Nomenclature). Sem resposta do MAST, só o Gaia DR3 |
| Coordenadas (RA, Dec) | Cole o campo "Coordenadas J2000 (colar no VSX)" (graus, 6 casas, sem arredondar; a forma sexagesimal está no campo ao lado) e clique em **Spot Check** (veja abaixo como ler o resultado). O texto do formulário sugere UCAC3 ou 2MASS, mas o Gaia DR3 é mais preciso e é o que o guia atual do VSX recomenda. A posição do Gaia é da época 2016; numa estrela comum o movimento próprio em 16 anos fica bem abaixo de 1", sem efeito na identificação |
| Tipo de variável | O tipo que você decidiu no passo 1 (EA, EB, EW, ROT...; veja [Os tipos de variável](#os-tipos-de-variável)) no menu **Standardized type**; deixe **Customized type** vazio. Marque **Uncertain** só se a página não confirmou o tipo (sem tipo provável, ou escolhido por você na dúvida); entre dois tipos possíveis, escreva no Customized type com `|` (ex.: `ROT|EW`) |
| Período | "Período (d)" |
| Época | "Época do mínimo (BJD)". O VSX fala em HJD, mas aceita o BJD_TDB do TESS (a diferença é de cerca de um minuto); o comentário avisa isso |
| Magnitude máxima | "Magnitude V (máxima)", na banda V |
| Magnitude mínima | "Amplitude (mag, TESS)": marque **"Minimum is an amplitude"** e escreva **TESS** no campo de banda |
| Fonte dos dados | "TESS QLP (FFI)" e os setores da ficha. O guia do VSX recomenda o PDCSAP, que é do SPOC; para estrela observada só nas imagens completas (FFI), o QLP é o produto disponível |
| Anexos | A curva em fase `data/vsx/<tic>_fase.png` (obrigatória) e a figura da triagem `data/triagem/<tic>.png`. Mande as duas: o VSX avisa que a abertura do TESS junta luz de vizinhas até ~120", e o mapa por pixel da triagem é a prova de que o sinal vem do alvo. Em campo lotado, como no plano da Galáxia, mande também a carta de identificação `data/vsx/<tic>_carta.png` (DSS2 Red, 5'x5', alvo e vizinhas marcados), gerada pelo botão "Gerar carta de identificação" na aba Enviar |

O comentário em inglês gerado pela página diz como a estrela foi achada (TESS QLP e setores), o período medido com todos os setores (e por que é 2P, quando os eclipses pares e ímpares diferem), a época em BJD_TDB, a amplitude, que a variação fica abaixo da precisão do ASAS-SN e do ZTF quando é o caso (o VSX incentiva combinar com levantamentos de solo), o que as buscas no VSX e no VizieR acharam e, se houver, a vizinha e o que o mapa por pixel mostra.

### Como ler o Spot Check e o Check name

O **Spot Check** lista tudo o que o VSX conhece a até 120" da posição, não só a sua estrela, e o **Check name** procura nomes parecidos. Lista vazia: siga. Com objetos na lista, olhe a distância (coluna Dist.):

- **A poucos segundos de arco (até ~30"):** é a mesma estrela. Alguém já a submeteu; cancele.
- **Mais longe, mas com o mesmo período (ou metade, ou o dobro):** o sinal pode ser dessa vizinha, cuja luz se mistura à do alvo nos pixels de 21" do TESS. Não envie.
- **Mais longe e com outro período ou outro tipo:** é outra estrela. Para ela imitar o seu sinal, teria de variar muito mais: uma vizinha 10 vezes mais fraca (2,5 mag) precisaria perder 13% do próprio brilho para causar uma queda de 1,3% na luz somada. O mapa por pixel da triagem confirma: o pico do sinal fica no pixel do alvo, não no da vizinha. Siga, e cite a vizinha no comentário.

A página Fichas faz essa mesma leitura antes de você abrir o formulário: consulta o VSX no mesmo raio de 120", dá o veredito de cada objeto e já põe no comentário em inglês a variável mais próxima.

## 5. Depois de enviar

1. No app, página **Fichas**, marque **Enviada ao VSX** na estrela.
2. O moderador responde por e-mail ou pelo próprio VSX. Se ele pedir ajuste, corrija e responda.
3. O aceite é marcado sozinho: ao abrir a página **Fichas**, o app consulta o VSX para cada estrela enviada e ainda não aceita. Quando aparece um objeto a até 10" da posição Gaia da ficha, a estrela vira **Aceita no VSX**, o nome que ela recebeu é preenchido e o app avisa "TIC X aceita no VSX como NOME". Se o VSX estiver fora do ar, marque à mão.

Os detalhes de cada item (P ou 2P, faixa de magnitude, por que a amplitude do TESS) estão no checklist da seção 11 da [especificação](../especificacao.md).
