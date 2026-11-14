# Rascunhos de discussões

Prontos para publicar quando as Discussions forem ativadas no repositório (Settings, Features). Uma seção por discussão, na ordem de publicação. A categoria vai na linha abaixo do título.

## Treino: casos que pareceram ambíguos

Categoria: Q&A

O treino mostra casos de resposta conhecida: variáveis já catalogadas e sinais que o pipeline descartou. A resposta vem do catálogo, mas nem sempre ela é a leitura mais natural da figura.

Quero saber onde o gabarito parece errado. Um caso em que a curva dobrada não mostra o período do catálogo, um mapa com o pico do sinal longe do alvo, um tipo que não combina com a forma da curva. O número do caso e o TIC bastam: são estrelas já publicadas.

Se o gabarito estiver errado, o caso sai do quiz. Se a explicação estiver fraca, ela melhora. Os dois ajudam mais do que qualquer caso novo.

Perguntas: qual caso te deixou em dúvida, e o que a figura mostrava?

## Qual campo do céu rodar depois

Categoria: Ideas

O `python -u pipeline.py --proximo` escolhe sozinho o próximo campo, por `src/campos.py`. A grade fica no plano da Via Láctea, começa em Cygnus (l=80, b=0), anda de 2,5 em 2,5 graus e depois abre faixas de 3, 6 e 9 graus para os dois lados. Pula ponto perto de campo já feito e ponto sem setor do TESS com cadência de 200 s.

A ordem atual é geográfica, não científica. Um campo perto do plano tem mais estrelas, mas também mais confusão. Uma região pouco estudada pode render mais por estrela.

Perguntas: qual região você rodaria primeiro, e por quê? Vale a pena priorizar por densidade, por época do ano ou por algo que os catálogos já mostram?

## Catálogos de variáveis que faltam na Fase 5

Categoria: Ideas

A Fase 5 cruza os sinais com o VSX, o ATLAS, o TESS-EBs, o ZTF, o ASAS-SN, o Wang+2025, o Gaia DR3, o TOI e o SIMBAD. A lista fica em `CATALOGOS_VIZIER`, no `config.py`.

Ela cresceu por necessidade. Uma candidata já publicada como pulsante SPB apareceu na busca do VizieR inteiro da Fase 8, e o catálogo entrou no cruzamento. Deve haver outros assim.

O que serve: o identificador do VizieR, a coluna de período e o raio em que o catálogo vale. Catálogo sem período também ajuda, se marcar a estrela como variável.

Perguntas: qual catálogo você sente falta? Algum já te fez perder tempo com uma candidata conhecida?

## Primeira submissão ao VSX: o que aprendi

Categoria: Show and tell

Rascunho. Preencher depois da primeira submissão.

O que quero contar aqui: como foi criar a conta na AAVSO, o que o formulário pede além da ficha, quanto tempo o moderador levou, o que ele pediu para corrigir e como ficou o nome no catálogo.

Lacunas: data do envio, número de estrelas, resposta do moderador, tempo até a aceitação.

Até lá, o caminho está no README, no passo a passo. Se você já submeteu uma variável, conte como foi: a experiência de quem passou primeiro vale mais do que o guia.

## Apresente-se

Categoria: General

Este espaço é para quem chegou agora. Conte o que te trouxe ao projeto: curiosidade por estrelas variáveis, vontade de aprender Python com um problema de verdade, ou os dois.

Também vale dizer o que você usa: sistema operacional, se já rodou o pipeline, se só abriu o treino online. Isso ajuda a saber onde o projeto trava para quem chega.

Perguntas: de onde você veio, e o que gostaria de ver no projeto?
