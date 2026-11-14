# Como submeter uma candidata ao VSX

O VSX (The International Variable Star Index) é o catálogo de estrelas variáveis da AAVSO. A submissão é feita à mão, pelo site [vsx.aavso.org](https://vsx.aavso.org): não há envio automático. Um moderador confere três coisas: a estrela está identificada certo, é variável e ainda não era conhecida. Conte com semanas até a resposta.

Faça uma estrela por vez. A AAVSO recomenda que as primeiras submissões de quem está começando sejam individuais.

## 1. Antes de abrir o formulário

Na página **Fichas** do app, para a estrela escolhida:

1. **Leia os avisos da ficha.** Aviso que diz "Não submeta" impede o envio. Aviso que diz "Pode submeter" é só informativo.
2. **Decida o tipo.** Se a ficha sugere "ROT, EW ou pulsante", escolha pela forma da curva em fase: dois mínimos iguais e curva contínua indicam EW (binária de contato); onda única e suave, ROT (mancha) ou pulsante. Na dúvida, prefira a estrela seguinte e deixe essa para depois.
3. **Confira o período.** Com o alerta "períodos dos setores não alinham", abra a figura e veja se os eclipses de setores diferentes caem no mesmo lugar. Se não caem, o período ainda não está bom para enviar.
4. **Veja a vizinha.** Com "Suspeito de blend: sim", confira no mapa por pixel da Revisão se o pico do sinal está no alvo. Se estiver, siga e mencione a vizinha no comentário da submissão.
5. **Busque no VSX online.** Em [vsx.aavso.org](https://vsx.aavso.org), use a busca por coordenadas com a RA e a Dec da ficha e raio de 1 minuto de arco. Se a estrela já aparece, alguém submeteu antes: não envie.

## 2. Criar o login no VSX

1. Em [vsx.aavso.org](https://vsx.aavso.org), clique em **Register** no menu do topo.
2. Preencha o formulário (o nome de login tem de 6 a 12 caracteres) e clique em **Register**.
3. Abra o e-mail de confirmação e clique no link: o login só funciona depois disso.

O login do VSX é separado da conta do site da AAVSO.

## 3. Abrir o formulário

1. Clique em **Log In** e entre.
2. Clique em **Submit** no menu do topo.
3. Escolha o **New Star Wizard**. Ele pede os campos um de cada vez e explica cada um. O **New Star Form** pede os mesmos dados numa página só; use-o quando já conhecer o caminho.

## 4. Copiar os campos da ficha

Cada campo da página Fichas tem um botão de copiar. Os nomes no formulário podem variar um pouco; a correspondência é esta:

| No formulário do VSX | Da ficha |
|---|---|
| Nome e identificadores | "Outros nomes": o TIC e o Gaia DR3. Se quiser, dê um nome provisório seu (ex.: "VGL V1") |
| Coordenadas (RA, Dec) | "RA (Gaia DR3)" e "Dec (Gaia DR3)", em graus |
| Tipo de variável | O tipo que você decidiu no passo 1 (EA, EB, EW, ROT...) |
| Período | "Período (d)" |
| Época | "Época do mínimo (BJD)" |
| Magnitude máxima | "Magnitude V (máxima)", na banda V |
| Magnitude mínima | "Amplitude (mag, TESS)": marque **"Minimum is an amplitude"** e escreva **TESS** no campo de banda |
| Fonte dos dados | TESS, QLP, e os setores da ficha |
| Anexos | A curva em fase `data/vsx/<tic>_fase.png` (obrigatória) e a figura da triagem `data/triagem/<tic>.png` |

No comentário, escreva em inglês e em poucas linhas como achou a estrela: curvas do TESS (QLP), período medido com todos os setores, sem variável conhecida a 30" e, se for o caso, a vizinha e por que ela não explica o sinal.

## 5. Depois de enviar

1. No app, página **Fichas**, marque **Enviada ao VSX** na estrela.
2. O moderador responde por e-mail ou pelo próprio VSX. Se ele pedir ajuste, corrija e responda.
3. Quando a estrela aparecer no catálogo, marque **Aceita no VSX** e anote o nome que ela recebeu.

Os detalhes de cada item (P ou 2P, faixa de magnitude, por que a amplitude do TESS) estão no checklist da seção 11 da [especificação](../especificacao.md).
